"""验证编译约束及真实 Java Flowable → 官方 Python 客户端 → 业务工程链路。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/examples/diagnostic_demo'))
from flowable_bridge import compile_workflow, deploy, engine_request, b, f
from flowable_worker import execute, resolve

xml = (ROOT / 'src/views/ProcessDesigner/examples/diagnostic-demo.bpmn').read_text(encoding='utf-8')
compiled = compile_workflow(xml)
bindings = json.loads(compiled['files']['bindings.json'])['bindings']
assert len(bindings) == 7
engine_xml = ET.fromstring(compiled['files']['workflow.bpmn20.xml'])
assert len(engine_xml.findall('.//' + b('userTask'))) == len(bindings) + 1
assert len(engine_xml.findall('.//' + b('endEvent'))) == 3
assert len(engine_xml.findall('.//' + b('serviceTask'))) == 7
assert resolve({'values': ['$Inspect.data.0']}, {'Inspect': {'data': [42]}}) == {'values': [42]}

def reject(transform):
    root = ET.fromstring(xml)
    transform(root)
    try:
        compile_workflow(ET.tostring(root, encoding='unicode'))
    except ValueError:
        return
    raise AssertionError('Invalid workflow accepted')

reject(lambda root: root.find('.//' + b('task')).attrib.pop(f('pythonModule')))
reject(lambda root: root.find('.//' + b('task')).set(f('pythonArguments'), '[]'))
reject(lambda root: root.find('.//' + b('task')).set(f('pythonFunction'), 'invalid()'))
reject(lambda root: root.find('.//' + b('sequenceFlow')).set('targetRef', 'Repair'))
reject(lambda root: root.find('.//' + b('task')).set(f('assessment'), ''))
try:
    execute({'module': 'diagnostic_demo.api', 'function': 'machine_action', 'kwargs': {},
             'outgoing': ['a', 'b']}, {})
except ValueError:
    pass
else:
    raise AssertionError('Invalid branch result accepted')
print('Compilation, bindings, required fields and invalid branch result checks passed', flush=True)

if '--unit-only' in sys.argv:
    sys.exit(0)

with tempfile.TemporaryDirectory(prefix='flowable-smoke-') as temp:
    manifest_file = Path(temp) / 'bindings.json'
    manifest_file.write_text(compiled['files']['bindings.json'], encoding='utf-8')
    log_file = (ROOT / 'backend/.local/flowable-worker-smoke.log')
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open('w', encoding='utf-8') as log:
        worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'backend/flowable_worker.py'),
            str(manifest_file), '--project', str(ROOT / 'backend/examples/diagnostic_demo')], stdout=log, stderr=log)
        try:
            deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
            definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]
            for scenario, terminal in [('normal', 'Solved'), ('recover', 'Solved'), ('action', 'Solved'),
                                       ('escalate', 'Escalation'), ('severe', 'Escalation'), ('jump', 'Jump_handoff')]:
                started = engine_request('/process-api/runtime/process-instances', json.dumps({
                    'processDefinitionId': definition['id'], 'variables': [{'name': 'scenario', 'type': 'string', 'value': scenario}]
                }).encode())
                run_id = started['id']
                deadline = time.monotonic() + 90
                while True:
                    history = engine_request('/process-api/history/historic-process-instances/' + run_id)
                    if history.get('endTime'):
                        break
                    review = engine_request('/diagnosis-api/instances/' + run_id + '/review')
                    if review['pending']:
                        assert scenario in ('escalate', 'severe')
                        engine_request('/diagnosis-api/instances/' + run_id + '/review', json.dumps({
                            'action': 'confirm', 'taskId': review['taskId'], 'reason': 'Smoke test confirmation'}).encode())
                    if time.monotonic() > deadline or worker.poll() is not None:
                        raise AssertionError(f'{scenario} did not finish; inspect {log_file}')
                    time.sleep(0.5)
                variables = engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=100')
                results = {item['variable']['name']: item['variable']['value'] for item in variables['data']}
                chart = Path(results['Inspect']['chart'])
                assert chart.is_file() and '<polyline' in chart.read_text()
                assert results['Inspect']['abnormal'] == (scenario != 'normal')
                activities = engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&size=100')
                visited = {item['activityId'] for item in activities['data']}
                assert terminal in visited, visited
                assert ('Action' in visited) == (scenario == 'action')
                assert ('Deep' in visited) == (scenario == 'escalate')
                assert ('Jump' in visited) == (scenario == 'jump')
                print(f'{scenario}: {terminal}; real SVG: {chart}; run: {run_id}', flush=True)
        finally:
            worker.terminate()
            worker.wait(timeout=10)
print('All six scenarios completed through real Flowable and official Python client', flush=True)
