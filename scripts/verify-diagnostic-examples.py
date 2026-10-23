"""真实运行新增示例，验证重试次数、支路互斥、汇合及顺序处置。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/examples/diagnostic_demo')]
from flowable_bridge import compile_workflow, deploy, engine_request
from flowable_worker import execute, resolve

EXAMPLES = {
    'voltage-diagnosis.bpmn': [('normal', 'Solved'), ('recover', 'Solved'), ('severe', 'Escalation')],
    'communication-retry.bpmn': [('normal', 'Solved'), ('recover', 'Solved'), ('offline', 'Escalation')],
    'sensor-comparison.bpmn': [('normal', 'Solved'), ('sensor-a', 'Solved'), ('sensor-b', 'Solved'), ('severe', 'Escalation')],
    'pressure-recovery.bpmn': [('stable', 'Solved'), ('leak', 'Escalation'), ('unknown', 'PressureJump_handoff')],
}

assert resolve('$$sensor-input', {}) == '$sensor-input'
assert execute({'module': 'diagnostic_demo.scenarios', 'function': 'check_link',
                'kwargs': {'context': '$', 'scenario': 'normal'}, 'outgoing': ['L_ready', 'L_retry']}, {})['connected']
print('PASS: literal dollar arguments and async business interfaces', flush=True)

with tempfile.TemporaryDirectory(prefix='diagnostic-examples-') as temporary:
    for filename, scenarios in EXAMPLES.items():
        xml = (ROOT / 'src/views/ProcessDesigner/examples' / filename).read_text(encoding='utf-8')
        compiled = compile_workflow(xml)
        if '--compile-only' in sys.argv:
            print('Compiled: ' + filename)
            continue
        manifest = Path(temporary) / 'bindings.json'
        manifest.write_text(compiled['files']['bindings.json'], encoding='utf-8')
        log_file = ROOT / 'backend/.local' / (filename + '.log')
        with log_file.open('w', encoding='utf-8') as log:
            worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'backend/flowable_worker.py'),
                str(manifest), '--project', str(ROOT / 'backend/examples/diagnostic_demo')], stdout=log, stderr=log)
            try:
                deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
                definitions = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])
                for scenario, terminal in scenarios:
                    run = engine_request('/process-api/runtime/process-instances', json.dumps({
                        'processDefinitionId': definitions['data'][0]['id'],
                        'variables': [{'name': 'scenario', 'type': 'string', 'value': scenario}]}).encode())
                    run_id = run['id']
                    deadline = time.monotonic() + 45
                    while not engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime'):
                        review = engine_request('/diagnosis-api/instances/' + run_id + '/review')
                        if review['pending']:
                            assert terminal == 'Escalation'
                            engine_request('/diagnosis-api/instances/' + run_id + '/review', json.dumps({
                                'action': 'confirm', 'taskId': review['taskId'], 'reason': 'Example verification'}).encode())
                        if time.monotonic() > deadline or worker.poll() is not None:
                            raise AssertionError(f'{filename}/{scenario} did not finish; inspect {log_file}')
                        time.sleep(0.3)
                    activities = engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&size=200&sort=startTime&order=asc')['data']
                    visited = [activity['activityId'] for activity in activities if activity['activityType'] in ('externalWorkerServiceTask', 'endEvent')]
                    variables = engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=100')['data']
                    values = {item['variable']['name']: item['variable']['value'] for item in variables}
                    assert terminal in visited, visited
                    ends = [a['activityId'] for a in activities if a['activityType'] == 'endEvent']
                    assert ends == [terminal], ends
                    charts = [value['chart'] for value in values.values() if isinstance(value, dict) and 'chart' in value]
                    assert charts and all(Path(chart).is_file() for chart in charts)
                    if filename == 'communication-retry.bpmn':
                        attempts = 1 if scenario == 'normal' else 3
                        assert visited.count('LinkCheck') == attempts
                        assert visited.count('RetryAction') == attempts - 1
                        assert values['LinkCheck']['attempt'] == attempts
                    elif filename == 'sensor-comparison.bpmn':
                        assert ('SensorA' in visited) == (scenario in ('sensor-a', 'severe'))
                        assert ('SensorB' in visited) == (scenario == 'sensor-b')
                        assert visited.count('SensorConclusion') == 1
                        assert values['ReadSensors']['source'] == '$sensor-input'
                    elif filename == 'pressure-recovery.bpmn':
                        assert visited.index('Vent') < visited.index('Reset') < visited.index('PressureDeep')
                        assert values['Reset']['reset'] is True
                    print(f'{filename}/{scenario}: {" -> ".join(visited)}; SVG files: {len(charts)}', flush=True)
            finally:
                worker.terminate()
                worker.wait(timeout=10)
print('PASS: diagnostic example checks', flush=True)
