"""验证完整冷却工程：独立运行、HTTP 接入、真实 Flowable 并行与串行。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'backend/examples/cooling_project'
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import deploy, engine_request
from python_sessions import stop_process
from server import create_server


def post(path, value):
    return engine_request(path, json.dumps(value).encode())


def wait(check):
    for _ in range(300):
        result = check()
        if result:
            return result
        time.sleep(0.15)
    raise AssertionError('Timed out waiting for cooling example')


def values(run_id):
    return {entry['variable']['name']: entry['variable']['value'] for entry in
            engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=1000')['data']}


def activities(run_id):
    return engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&size=1000')['data']


def finished(run_id):
    return engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime')


def review(run_id):
    result = engine_request('/diagnosis-api/instances/' + run_id + '/review')
    return result if result.get('pending') else None


def confirm_actions_until(run_id, condition):
    # 冷却工程处置接口执行后必须先人工核验；保留原脚本在 success 停点的断言。
    def advance():
        state = review(run_id)
        if state and state.get('mode') == 'action':
            post('/diagnosis-api/instances/' + run_id + '/review', {
                'action': 'confirm', 'taskId': state['taskId'], 'next': 'ok'})
        return condition()
    return wait(advance)


def verify():
    reports = []
    for scenario, expected in [('fan', 0), ('filter', 0), ('healthy', 0), ('unknown', 2), ('fan_stuck', 1)]:
        completed = subprocess.run([sys.executable, str(PROJECT / 'run_demo.py'), '--scenario', scenario],
                                   capture_output=True, text=True, encoding='utf-8', timeout=15)
        assert completed.returncode == expected, (scenario, completed.stderr)
        if expected == 0:
            assert json.loads(completed.stdout)['after'] == 42
        elif scenario == 'fan_stuck':
            assert 'Fan restart failed' in completed.stderr and 'simulator.py' in completed.stderr
    print('PASS: standalone Python project, five scenarios and original exception', flush=True)

    with tempfile.TemporaryDirectory(prefix='cooling-example-') as temporary:
        directory = Path(temporary)
        registration = {'name': 'Cooling verification', 'path': str(PROJECT), 'module': 'cooling_lab.api',
                        'factory': 'CoolingSession',
                        'python': sys.executable}
        server = create_server(0, registry_file=directory / 'registry.json')
        server.RequestHandlerClass.log_message = lambda *args: None
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        def api(path, data):
            request = Request(f'http://127.0.0.1:{server.server_port}/api/projects' + path,
                              json.dumps(data).encode(), {'Content-Type': 'application/json'})
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        try:
            project = api('', registration)['project']
            assert len(project['interfaces']) == 11
            before = api('/' + project['id'] + '/call', {'function': 'summary', 'inputs': {'scenario': 'fan'}})
            assert before['result']['temperature'] == 85
            session_id = before['sessionId']
            repaired = api('/' + project['id'] + '/call', {'function': 'restart_fan', 'sessionId': session_id})
            assert repaired['result'] is None
            after = api('/' + project['id'] + '/call', {'function': 'summary', 'sessionId': session_id})
            assert after['result']['temperature'] == 42 and after['result']['repairs'] == ['restart_fan']
            api('/' + project['id'] + '/sessions/close', {'sessionId': session_id})
        finally:
            server.shutdown()
            server.server_close()
            serving.join(timeout=5)
        print('PASS: real HTTP registration, signature discovery and reusable debug session', flush=True)

        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
        local_registry = directory / 'engine-projects.json'
        local_registry.write_text(json.dumps({'cooling': registration}), encoding='utf-8')
        with (directory / 'engine.log').open('w', encoding='utf-8') as log:
            engine = subprocess.Popen(['java', '-jar', str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:cooling;DB_CLOSE_DELAY=-1'],
                cwd=directory, stdout=log, stderr=log)
            workers = []
            try:
                def ready():
                    if engine.poll() is not None:
                        raise AssertionError('Temporary Flowable exited')
                    try:
                        return engine_request('/process-api/management/engine')
                    except RuntimeError:
                        return False
                wait(ready)
                definitions = {}
                for mode in ('parallel', 'serial'):
                    bundle = ROOT / 'backend/.local' / ('cooling-example-' + mode)
                    assert (bundle / 'bindings.json').exists(), 'Prepare both modes before verification'
                    workers.append(subprocess.Popen([sys.executable, '-u', str(ROOT / 'backend/flowable_worker.py'),
                        str(bundle / 'bindings.json'), '--registry', str(local_registry)], cwd=directory, stdout=log, stderr=log))
                    deployment = deploy((bundle / 'workflow.bpmn20.xml').read_text(encoding='utf-8'))
                    definitions[mode] = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
                def start(mode, scenario):
                    return post('/process-api/runtime/process-instances', {'processDefinitionId': definitions[mode],
                        'variables': [{'name': 'scenario', 'type': 'string', 'value': scenario},
                                      {'name': 'device_id', 'type': 'string', 'value': 'CHECK-' + scenario}]})['id']
                runs = {scenario: start('parallel', scenario) for scenario in ('fan', 'filter', 'healthy', 'unknown', 'fan_stuck')}
                for scenario in ('fan', 'filter', 'healthy', 'unknown'):
                    run_id = runs[scenario]
                    confirm_actions_until(run_id, lambda: finished(run_id))
                    result = values(run_id)
                    expected_status = 'failed' if scenario == 'unknown' else 'problemSolved'
                    assert result['diagnosticStatus'] == expected_status, (scenario, result)
                    expected_failures = 2 if scenario == 'unknown' else 0 if scenario == 'healthy' else 1
                    assert len(result.get('diagnosticFailures', [])) == expected_failures, (scenario, result)
                    if scenario != 'healthy':
                        for node_id in ('air_sample', 'fan_sample'):
                            assert result[node_id]['native'] and result[node_id]['pythonType'].endswith('.Measurement')
                    if scenario != 'unknown':
                        report_key = {'fan': 'FanReport', 'filter': 'FilterReport', 'healthy': 'NormalReport'}[scenario]
                        report = result[report_key]
                        assert report['after'] == 42 and '<svg ' in report['chartSvg'] and report['device_id'] == 'CHECK-' + scenario
                        assert report['repairs'] == ([] if scenario == 'healthy' else ['restart_fan'] if scenario == 'fan' else ['clean_filter'])
                    reports.append({'mode': 'parallel', 'scenario': scenario, 'status': expected_status,
                                    'failedPaths': expected_failures, 'runId': run_id})
                broken = runs['fan_stuck']
                jobs = wait(lambda: engine_request('/process-api/management/deadletter-jobs?processInstanceId=' + broken)['data'])
                trace = engine_request('/process-api/management/deadletter-jobs/' + jobs[0]['id'] + '/exception-stacktrace', as_text=True)
                assert 'Fan restart failed' in trace and 'simulator.py' in trace
                assert not any(item['activityId'] == 'Solved' for item in activities(broken))
                reports.append({'mode': 'parallel', 'scenario': 'fan_stuck', 'status': 'taskError', 'runId': broken})
                print('PASS: real Flowable parallel five scenarios, native objects, SVG, failure isolation and exception', flush=True)

                serial_fan = start('serial', 'fan')
                confirm_actions_until(serial_fan, lambda: finished(serial_fan))
                result = values(serial_fan)
                assert result['FanReport']['after'] == 42 and result['diagnosticFailures'][0]['nodeId'] == 'FilterCheck'
                reports.append({'mode': 'serial', 'scenario': 'fan', 'status': 'problemSolved', 'runId': serial_fan})
                for choice in ('finish', 'continue'):
                    run_id = start('serial', 'filter')
                    pending = confirm_actions_until(run_id, lambda: (
                        state if (state := review(run_id)) and state.get('mode') == 'success' else None))
                    assert pending['mode'] == 'success'
                    assert values(run_id)['diagnosticStatus'] == 'paused'
                    assert not any(item['activityId'] == 'fan_sample' for item in activities(run_id))
                    post('/diagnosis-api/instances/' + run_id + '/review', {'action': 'confirm',
                         'taskId': pending['taskId'], 'next': choice})
                    wait(lambda: finished(run_id))
                    visited = activities(run_id)
                    assert any(item['activityId'] == 'fan_sample' for item in visited) == (choice == 'continue')
                    assert sum(item['activityId'] == 'CleanFilter' for item in visited) == 1
                    assert values(run_id)['diagnosticStatus'] == 'problemSolved'
                    reports.append({'mode': 'serial', 'scenario': 'filter', 'choice': choice, 'status': 'problemSolved', 'runId': run_id})
                unknown = start('serial', 'unknown')
                wait(lambda: finished(unknown))
                assert values(unknown)['diagnosticStatus'] == 'failed'
                reports.append({'mode': 'serial', 'scenario': 'unknown', 'status': 'failed', 'runId': unknown})
                print('PASS: real Flowable serial failure continuation, success pause/finish/continue and no repeated repair', flush=True)
            except Exception:
                print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-18000:])
                raise
            finally:
                for worker in workers:
                    stop_process(worker)
                stop_process(engine)
    output = ROOT / 'backend/.local/cooling-example-verification.json'
    output.write_text(json.dumps({'passed': True, 'cases': reports}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verified cases: ' + str(len(reports)) + '; report: ' + str(output), flush=True)


if __name__ == '__main__':
    verify()
