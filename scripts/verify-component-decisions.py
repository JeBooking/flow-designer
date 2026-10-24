"""真实引擎验证：关闭人工开关，仍由 Python 组件发起等待、分支选择和回退。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, deploy, engine_request, b, f


def post(path, body):
    return engine_request(path, json.dumps(body).encode())


def wait_review(path, node):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = engine_request(path)
        if state['pending'] and state['nodeId'] == node:
            return state
        time.sleep(0.2)
    raise AssertionError('Expected component-requested human wait at ' + node)


root = ET.fromstring((ROOT / 'src/views/ProcessDesigner/examples/voltage-diagnosis.bpmn').read_text(encoding='utf-8'))
for task in root.findall('.//' + b('task')):
    task.attrib.pop(f('humanDecision'), None)
    if task.get('id') in ('VoltageConclusion', 'Reseat'):
        task.set(f('pythonModule'), 'diagnostic_demo.decisions')
        conclusion = task.get('id') == 'VoltageConclusion'
        task.set(f('pythonFunction'), 'review_voltage' if conclusion else 'review_recovery')
        task.set(f('pythonArguments'), json.dumps({'reading' if conclusion else 'data': '$Voltage'}))
bundle = compile_workflow(ET.tostring(root, encoding='unicode'))
assert all(not item['humanDecision'] for item in json.loads(bundle['files']['bindings.json'])['bindings'].values())
with tempfile.TemporaryDirectory(prefix='component-decisions-') as temp:
    bindings = Path(temp) / 'bindings.json'
    bindings.write_text(bundle['files']['bindings.json'], encoding='utf-8')
    with (ROOT / 'backend/.local/component-decisions.log').open('w', encoding='utf-8') as log:
        worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'backend/flowable_worker.py'),
            str(bindings), '--project', str(ROOT / 'backend/examples/diagnostic_demo')], stdout=log, stderr=log)
        try:
            deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
            definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
            instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                'variables': [{'name': 'scenario', 'type': 'string', 'value': 'recover'}]})['id']
            path = '/diagnosis-api/instances/' + instance + '/review'
            first = wait_review(path, 'VoltageConclusion')
            assert first['evidence']['minimum'] == 21.2 and first['evidence']['chartSvg']
            assert 'Check the voltage' in first['instructions']['assessment']
            assert {item['id'] for item in first['candidates']} == {'Voltage'}
            post(path, {'taskId': first['taskId'], 'action': 'confirm'})
            recovery = wait_review(path, 'Reseat')
            assert {item['id'] for item in recovery['options']} == {'V_solved', 'V_escalate'}
            post(path, {'taskId': recovery['taskId'], 'action': 'recheck',
                'targetNodeId': 'Voltage', 'reason': 'Repeat acquisition for component decision'})
            repeated = wait_review(path, 'VoltageConclusion')
            values = {row['name']: row['value'] for row in engine_request('/process-api/runtime/process-instances/' + instance + '/variables')}
            assert 'request_Reseat' not in values and 'human_Reseat' not in values
            assert repeated['taskId'] != first['taskId']
            post(path, {'taskId': repeated['taskId'], 'action': 'confirm'})
            recovery = wait_review(path, 'Reseat')
            post(path, {'taskId': recovery['taskId'], 'action': 'confirm', 'next': 'V_solved'})
            deadline = time.monotonic() + 10
            while not engine_request('/process-api/history/historic-process-instances/' + instance).get('endTime'):
                assert time.monotonic() < deadline
                time.sleep(0.2)
            print('PASS: automatic acquisition skips review; base/decorator request human judgment without flags; evidence, routes, recheck and cleanup work')
        finally:
            worker.terminate()
            worker.wait(timeout=10)
