"""隔离验证真实目录导入、动作确认和纯人工流程；不连接现有服务或设备。"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, deploy, engine_request
from python_sessions import stop_process
from server import create_server


# 使用前端实际目录恢复器；只在临时目录打包，不复制业务 BPMN XML。
IMPORTER = r'''
import { createRequire } from 'node:module'
import { readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
const [root, project, directory, mode, identity] = process.argv.slice(2)
const require = createRequire(path.join(root, 'package.json'))
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const bundle = path.join(directory, 'directory.mjs')
await build({ entryPoints: [path.join(root,
  'src/views/ProcessDesigner/CodeGeneration/projectDirectory.ts')],
  outfile: bundle, bundle: true, platform: 'node', format: 'esm',
  alias: { '@': path.join(root, 'src') } })
const { importWorkflowDirectory } = await import(pathToFileURL(bundle))
const entries = []
async function walk(relative = '') {
  for (const entry of await readdir(path.join(project, relative), { withFileTypes: true })) {
    if (entry.name.startsWith('.') || ['__pycache__', 'output'].includes(entry.name)) continue
    const name = path.posix.join(relative, entry.name)
    if (entry.isDirectory()) await walk(name)
    else entries.push({ path: path.basename(project) + '/' + name, read: async () => {
      const bytes = await readFile(path.join(project, name))
      if (name !== 'workflow.json') return new Uint8Array(bytes)
      const definition = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, ''))
      definition.mode = mode
      definition.process.id += identity
      return new TextEncoder().encode(JSON.stringify(definition))
    } })
  }
}
await walk()
const restored = await importWorkflowDirectory(entries)
if (restored.missingResources.length) throw new Error(JSON.stringify(restored.missingResources))
await writeFile(path.join(directory, identity + '.bpmn'), restored.xml)
'''


def post(path, body):
    return engine_request(path, json.dumps(body).encode())


def wait(check, description):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.15)
    raise AssertionError('Timed out: ' + description)


def review(run_id):
    return engine_request('/diagnosis-api/instances/' + run_id + '/review')


def pending(run_id, node_id):
    state = review(run_id)
    return state if state.get('pending') and state.get('nodeId') == node_id else None


def choose(run_id, state, next_value=None):
    body = {'action': 'confirm', 'taskId': state['taskId']}
    if next_value is not None:
        body['next'] = next_value
    return post('/diagnosis-api/instances/' + run_id + '/review', body)


def activities(run_id):
    return engine_request('/process-api/history/historic-activity-instances?processInstanceId='
                          + run_id + '&size=1000')['data']


def visited(run_id, node_id):
    return any(item['activityId'] == node_id for item in activities(run_id))


def values(run_id):
    rows = engine_request('/process-api/history/historic-variable-instances?processInstanceId='
                          + run_id + '&size=1000')['data']
    return {row['variable']['name']: row['variable']['value'] for row in rows}


def finished(run_id):
    return engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime')


def restore(project, directory, mode, identity):
    runner = directory / 'import.mjs'
    runner.write_text(IMPORTER, encoding='utf-8')
    subprocess.run(['node', str(runner), str(ROOT), str(project), str(directory), mode, identity],
                   cwd=ROOT, check=True, timeout=60)
    return (directory / (identity + '.bpmn')).read_text(encoding='utf-8')


def worker_interpreter():
    # 协调器依赖官方 SDK；业务工程只需标准库，不能用业务解释器替代协调器环境。
    override = os.environ.get('FLOWABLE_WORKER_PYTHON', '').strip()
    bundled = ROOT / 'backend/.local/venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    executable = override or (str(bundled) if bundled.is_file() else sys.executable)
    instruction = ('Prepare backend/.local/venv using backend/requirements-flowable.txt, '
                   'or set FLOWABLE_WORKER_PYTHON to an existing interpreter with the official SDK. '
                   'This script does not install dependencies.')
    try:
        checked = subprocess.run([executable, '-X', 'utf8', '-c',
            'from flowable.external_worker_client import ExternalWorkerClient; '
            'from requests.auth import HTTPBasicAuth'], capture_output=True, text=True,
            encoding='utf-8', timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError('Worker interpreter unavailable: ' + executable + '. ' + instruction) from error
    if checked.returncode:
        raise RuntimeError('Worker dependencies unavailable: ' + executable + '\n' + instruction
                           + '\n' + checked.stderr)
    return executable


def verify():
    worker_python = worker_interpreter()
    previous_host = os.environ.get('FLOWABLE_URL')
    reports = []
    with tempfile.TemporaryDirectory(prefix='action-confirmation-') as temporary:
        directory = Path(temporary)
        trace = directory / 'action-calls.jsonl'
        cooling = directory / 'cooling_project'
        shutil.copytree(ROOT / 'backend/examples/cooling_project', cooling,
                        ignore=shutil.ignore_patterns('.*', '__pycache__', 'output'))
        # 只扩展临时模拟设备配置，让同一流程同时到达两个处置停点。
        scenarios_file = cooling / 'assets/scenarios.json'
        scenarios = json.loads(scenarios_file.read_text(encoding='utf-8'))
        scenarios['both'] = {**scenarios['fan'], 'filter_blocked': True}
        scenarios_file.write_text(json.dumps(scenarios), encoding='utf-8')
        # repairs 本身幂等，单看最终 repairs 无法证明只调用一次；临时副本记录每次真实方法入口。
        session_file = cooling / 'src/cooling_lab/session.py'
        source = session_file.read_text(encoding='utf-8')
        for function, asynchronous in [('clean_filter', False), ('restart_fan', True)]:
            signature = ('    async def ' if asynchronous else '    def ') + function + '(self) -> None:\n'
            assert signature in source
            source = source.replace(signature, signature +
                '        with open(' + repr(str(trace)) + ", 'a', encoding='utf-8') as action_trace:\n" +
                '            action_trace.write(__import__(\'json\').dumps({\'device\': self.device.device_id, '
                + repr('function') + ': ' + repr(function) + "}) + '\\n')\n")
        session_file.write_text(source, encoding='utf-8')

        def calls(device_id, function):
            if not trace.exists():
                return 0
            return sum(json.loads(line) == {'device': device_id, 'function': function}
                       for line in trace.read_text(encoding='utf-8').splitlines())

        with socket.socket() as available:
            available.bind(('127.0.0.1', 0))
            port = available.getsockname()[1]
        os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
        workers = []
        server = None
        serving = None
        engine = None
        try:
            with (directory / 'engine.log').open('w', encoding='utf-8') as log:
                engine = subprocess.Popen(['java', '-jar',
                    str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                    f'--server.port={port}',
                    '--spring.datasource.url=jdbc:h2:mem:action_confirmation;DB_CLOSE_DELAY=-1'],
                    cwd=directory, stdout=log, stderr=log)

                def ready():
                    if engine.poll() is not None:
                        raise AssertionError('Temporary Flowable exited')
                    try:
                        return engine_request('/process-api/management/engine')
                    except RuntimeError:
                        return False
                wait(ready, 'temporary engine startup')

                # 此后端只处理纯人工启动，注册表始终为空；冷却 worker 独立读临时注册表。
                server = create_server(0, registry_file=directory / 'manual-registry.json')
                server.RequestHandlerClass.log_message = lambda *args: None
                serving = threading.Thread(target=server.serve_forever, daemon=True)
                serving.start()

                def backend_start(xml):
                    request = Request(f'http://127.0.0.1:{server.server_port}/api/flowable/start',
                        json.dumps({'xml': xml}).encode(), {'Content-Type': 'application/json'})
                    with urlopen(request, timeout=30) as response:
                        return json.load(response)['run']['id']

                for mode in ('parallel', 'serial'):
                    xml = restore(ROOT / 'backend/examples/manual_action_project', directory,
                                  mode, 'Manual' + mode)
                    manifest = json.loads(compile_workflow(xml)['files']['bindings.json'])
                    assert all(not binding['module'] for binding in manifest['bindings'].values())
                    run_id = backend_start(xml)
                    decision = wait(lambda: pending(run_id, 'ManualInspect'), 'manual inspection')
                    assert decision['mode'] == 'decision'
                    assert decision['instructions']['referenceImage'].startswith('data:')
                    choose(run_id, decision, 'yes')
                    state = wait(lambda: pending(run_id, 'ManualRemediation'), 'manual action')
                    assert state['mode'] == 'action' and state['actionMode'] == 'manual'
                    assert visited(run_id, 'ManualConclusion')
                    choose(run_id, state, 'not_ok')
                    unchanged = review(run_id)
                    assert unchanged['pending'] and unchanged['taskId'] == state['taskId']
                    assert not visited(run_id, 'Solved') and not finished(run_id)
                    choose(run_id, unchanged, 'ok')
                    wait(lambda: finished(run_id), 'manual completion')
                    assert values(run_id)['diagnosticStatus'] == 'problemSolved'
                    declined = backend_start(xml)
                    decision = wait(lambda: pending(declined, 'ManualInspect'), 'manual No branch')
                    choose(declined, decision, 'no')
                    escalation = wait(lambda: pending(declined, 'Escalation'), 'manual escalation')
                    assert not visited(declined, 'ManualRemediation')
                    choose(declined, escalation)
                    wait(lambda: finished(declined), 'escalation completion')
                    reports.append({'mode': mode, 'manual': 'yes/not_ok/ok and no/escalation'})
                assert not (directory / 'manual-registry.json').exists(), 'Manual start registered a project'

                registration = {'name': 'Isolated Cooling', 'path': str(cooling),
                    'module': 'cooling_lab.api', 'factory': 'CoolingSession', 'python': sys.executable}
                registry = directory / 'cooling-registry.json'
                registry.write_text(json.dumps({'cooling': registration}), encoding='utf-8')
                definitions = {}
                for mode in ('parallel', 'serial'):
                    xml = restore(cooling, directory, mode, 'Cooling' + mode)
                    compiled = compile_workflow(xml)
                    bindings = directory / (mode + '-bindings.json')
                    bindings.write_text(compiled['files']['bindings.json'], encoding='utf-8')
                    workers.append(subprocess.Popen([worker_python, '-u', '-X', 'utf8',
                        str(ROOT / 'backend/flowable_worker.py'), str(bindings), '--registry', str(registry)],
                        cwd=directory, stdout=log, stderr=log))
                    deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
                    definitions[mode] = engine_request('/process-api/repository/process-definitions?deploymentId='
                                                      + deployment['id'])['data'][0]['id']

                def start(mode, scenario):
                    device_id = mode + '-' + scenario
                    run_id = post('/process-api/runtime/process-instances', {
                        'processDefinitionId': definitions[mode], 'variables': [
                            {'name': 'scenario', 'type': 'string', 'value': scenario},
                            {'name': 'device_id', 'type': 'string', 'value': device_id}]})['id']
                    return run_id, device_id

                runs = {scenario: start('parallel', scenario) for scenario in ('fan', 'filter')}
                states = {}
                for scenario, (run_id, device_id) in runs.items():
                    action = 'RestartFan' if scenario == 'fan' else 'CleanFilter'
                    function = 'restart_fan' if scenario == 'fan' else 'clean_filter'
                    report = 'FanReport' if scenario == 'fan' else 'FilterReport'
                    state = wait(lambda: pending(run_id, action), 'parallel ' + action)
                    assert state['mode'] == 'action' and state['actionMode'] == 'confirm'
                    assert visited(run_id, 'FanConclusion' if scenario == 'fan' else 'FilterConclusion')
                    assert calls(device_id, function) == 1
                    assert not visited(run_id, report) and not visited(run_id, 'Solved')
                    choose(run_id, state, 'not_ok')
                    unchanged = review(run_id)
                    assert unchanged['pending'] and unchanged['taskId'] == state['taskId']
                    assert not visited(run_id, report) and not visited(run_id, 'Solved')
                    assert calls(device_id, function) == 1
                    states[scenario] = unchanged
                fan, fan_device = runs['fan']
                choose(fan, states['fan'], 'ok')
                wait(lambda: finished(fan), 'fan confirmation completion')
                other = review(runs['filter'][0])
                assert other['pending'] and other['taskId'] == states['filter']['taskId']
                choose(runs['filter'][0], other, 'ok')
                wait(lambda: finished(runs['filter'][0]), 'filter confirmation completion')
                for scenario, (run_id, device_id) in runs.items():
                    report = values(run_id)['FanReport' if scenario == 'fan' else 'FilterReport']
                    function = 'restart_fan' if scenario == 'fan' else 'clean_filter'
                    assert report['device_id'] == device_id and report['repairs'] == [function]
                    assert calls(device_id, function) == 1
                    assert values(run_id)['diagnosticStatus'] == 'problemSolved'
                    assert visited(run_id, 'air_sample') and visited(run_id, 'fan_sample')
                    reports.append({'mode': 'parallel', 'scenario': scenario, 'calls': 1})

                siblings, device_id = start('parallel', 'both')

                def sibling_reviews():
                    tasks = engine_request('/diagnosis-api/instances/' + siblings + '/review/tasks')['tasks']
                    return tasks if len(tasks) == 2 else None

                tasks = wait(sibling_reviews, 'two pending sibling actions')
                by_node = {task['nodeId']: task for task in tasks}
                assert set(by_node) == {'RestartFan', 'CleanFilter'}
                choose(siblings, by_node['CleanFilter'], 'not_ok')
                after = {task['nodeId']: task for task in sibling_reviews()}
                assert all(after[node]['taskId'] == task['taskId'] for node, task in by_node.items())
                assert not visited(siblings, 'Solved')
                assert not visited(siblings, 'FanReport') and not visited(siblings, 'FilterReport')
                choose(siblings, after['RestartFan'], 'ok')
                remaining = wait(lambda: pending(siblings, 'CleanFilter'), 'remaining sibling action')
                assert remaining['taskId'] == by_node['CleanFilter']['taskId']
                assert not finished(siblings) and not visited(siblings, 'FilterReport')
                choose(siblings, remaining, 'ok')
                wait(lambda: finished(siblings), 'both sibling confirmations')
                assert calls(device_id, 'restart_fan') == calls(device_id, 'clean_filter') == 1
                assert set(values(siblings)['FilterReport']['repairs']) == {'restart_fan', 'clean_filter'}
                reports.append({'mode': 'parallel', 'scenario': 'both',
                                'siblings': 'independent tasks, both calls exactly once'})

                run_id, device_id = start('serial', 'filter')
                state = wait(lambda: pending(run_id, 'CleanFilter'), 'serial action')
                assert state['mode'] == 'action'
                assert calls(device_id, 'clean_filter') == 1
                assert not visited(run_id, 'fan_sample') and not visited(run_id, 'FilterReport')
                choose(run_id, state, 'not_ok')
                unchanged = review(run_id)
                assert unchanged['pending'] and unchanged['taskId'] == state['taskId']
                assert not visited(run_id, 'fan_sample') and not visited(run_id, 'Solved')
                choose(run_id, unchanged, 'ok')
                success = wait(lambda: pending(run_id, 'Solved'), 'serial success review')
                assert success['mode'] == 'success'
                assert not visited(run_id, 'fan_sample')
                choose(run_id, success, 'continue')
                wait(lambda: finished(run_id), 'serial remaining queue')
                assert visited(run_id, 'fan_sample') and calls(device_id, 'clean_filter') == 1
                assert values(run_id)['FilterReport']['repairs'] == ['clean_filter']
                reports.append({'mode': 'serial', 'scenario': 'filter', 'calls': 1,
                                'queue': 'held until action OK and success continue'})
                print(json.dumps({'passed': True, 'cases': reports}, ensure_ascii=False, indent=2))
        except Exception:
            print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-18000:])
            raise
        finally:
            if server:
                server.shutdown()
                server.server_close()
            if serving:
                serving.join(timeout=5)
            for worker in workers:
                stop_process(worker)
            if engine:
                stop_process(engine)
            if previous_host is None:
                os.environ.pop('FLOWABLE_URL', None)
            else:
                os.environ['FLOWABLE_URL'] = previous_host


if __name__ == '__main__':
    verify()
