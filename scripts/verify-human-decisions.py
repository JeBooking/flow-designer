"""真实引擎与官方 worker 验证多个人工入口、人工分支及通用回退。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/examples/diagnostic_demo')]
from flowable_bridge import compile_workflow, deploy, engine_request, b, f
from flowable_worker import execute


def post(path, body):
    return engine_request(path, json.dumps(body).encode())


def wait_review(path, node):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = engine_request(path)
        if state['pending'] and state['nodeId'] == node:
            return state
        time.sleep(0.2)
    raise AssertionError('Expected human wait at ' + node)


def reject(path, state, body):
    try:
        post(path, {'taskId': state['taskId'], **body})
    except RuntimeError:
        assert engine_request(path)['taskId'] == state['taskId']
    else:
        raise AssertionError('Invalid request accepted: ' + str(body))


# 人工分支不要求业务函数提前给出 next，采集/绘图工程无需包含路由逻辑。
assert 'next' not in execute({'module': 'diagnostic_demo.scenarios', 'function': 'voltage',
    'kwargs': {'scenario': 'recover'}, 'outgoing': ['a', 'b'], 'humanDecision': True}, {})
xml = (ROOT / 'src/views/ProcessDesigner/examples/human-decision.bpmn').read_text(encoding='utf-8')
bundle = compile_workflow(xml)
with tempfile.TemporaryDirectory(prefix='human-decision-') as temp:
    bindings = Path(temp) / 'bindings.json'
    bindings.write_text(bundle['files']['bindings.json'], encoding='utf-8')
    with (ROOT / 'backend/.local/human-decision-smoke.log').open('w', encoding='utf-8') as log:
        worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'backend/flowable_worker.py'),
            str(bindings), '--project', str(ROOT / 'backend/examples/diagnostic_demo')], stdout=log, stderr=log)
        try:
            deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
            definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
            run_id = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                'variables': [{'name': 'scenario', 'type': 'string', 'value': 'recover'}]})['id']
            path = '/diagnosis-api/instances/' + run_id + '/review'
            first = wait_review(path, 'Voltage')
            assert first['candidates'] == [] and first['mode'] == 'decision'
            assert first['instructions']['assessment']
            reject(path, first, {'action': 'recheck', 'targetNodeId': 'Voltage', 'reason': 'Current node'})
            reject(path, first, {'action': 'recheck', 'targetNodeId': 'Reseat', 'reason': 'Unvisited'})
            post(path, {'action': 'confirm', 'taskId': first['taskId']})
            manual = wait_review(path, 'VoltageConclusion')
            assert {item['id'] for item in manual['candidates']} == {'Voltage'}
            post(path, {'action': 'recheck', 'taskId': manual['taskId'], 'targetNodeId': 'Voltage', 'reason': 'Repeat acquisition'})
            repeated = wait_review(path, 'Voltage')
            assert repeated['taskId'] != first['taskId']
            reject(path, repeated, {'action': 'confirm', 'taskId': first['taskId']})
            post(path, {'action': 'confirm', 'taskId': repeated['taskId']})
            manual = wait_review(path, 'VoltageConclusion')
            post(path, {'action': 'confirm', 'taskId': manual['taskId']})
            decision = wait_review(path, 'Reseat')
            assert {item['id'] for item in decision['candidates']} == {'Voltage', 'VoltageConclusion'}
            reject(path, decision, {'action': 'confirm'})
            reject(path, decision, {'action': 'confirm', 'next': 'V_start'})
            post(path, {'action': 'recheck', 'taskId': decision['taskId'], 'targetNodeId': 'VoltageConclusion', 'reason': 'Reconsider manual conclusion'})
            manual = wait_review(path, 'VoltageConclusion')
            values = {row['name']: row['value'] for row in engine_request('/process-api/runtime/process-instances/' + run_id + '/variables')}
            assert 'Voltage' in values and 'Reseat' not in values and 'VoltageConclusion' not in values
            post(path, {'action': 'confirm', 'taskId': manual['taskId']})
            decision = wait_review(path, 'Reseat')
            # Python 建议解决，人工可依据现场情况选择上升。
            post(path, {'action': 'confirm', 'taskId': decision['taskId'], 'next': 'V_escalate'})
            escalation = wait_review(path, 'Escalation')
            assert {item['id'] for item in escalation['candidates']} == {'Voltage', 'VoltageConclusion', 'Reseat'}
            post(path, {'action': 'recheck', 'taskId': escalation['taskId'], 'targetNodeId': 'Reseat', 'reason': 'Retry recovery action'})
            decision = wait_review(path, 'Reseat')
            post(path, {'action': 'confirm', 'taskId': decision['taskId'], 'next': 'V_solved'})
            deadline = time.monotonic() + 10
            while not engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime'):
                assert time.monotonic() < deadline
                time.sleep(0.2)
            rows = engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=100')['data']
            final = {row['variable']['name']: row['variable']['value'] for row in rows}
            audits = final['diagnosticReviews']
            assert sum(item['action'] == 'recheck' for item in audits) == 3
            override = next(item for item in audits if item.get('next') == 'V_escalate')
            assert override['previousResult']['next'] == 'V_solved'
            assert final['Reseat']['next'] == 'V_solved' and final['Reseat']['humanConfirmed']
            print('PASS: Python + human and manual-only nodes wait; all waits support recheck; branch override, action targets, cleanup, audit and stale/invalid rejection verified')
        finally:
            worker.terminate()
            worker.wait(timeout=10)

# 没有 worker 的纯人工链路也能选择分支；无出线的跳转节点仍可确认交接。
for handoff in (False, True):
    root = ET.fromstring(xml)
    process = root.find(b('process'))
    process.set('id', 'ManualHandoff' if handoff else 'ManualOnly')
    for task in list(process.findall(b('task'))):
        if task.get(f('diagnosisKind')) in ('problemSolved', 'escalation'):
            if handoff:
                process.remove(task)
            continue
        for field in ('pythonModule', 'pythonFunction', 'pythonArguments'):
            task.attrib.pop(f(field), None)
        if task.get('id') == 'Voltage':
            task.set(f('assessment'), '长文本 / Long instructions ' * 1000)
        if handoff and task.get('id') == 'Reseat':
            task.set(f('diagnosisKind'), 'jump')
    if handoff:
        for edge in list(process.findall(b('sequenceFlow'))):
            if edge.get('sourceRef') == 'Reseat':
                process.remove(edge)
    compiled = compile_workflow(ET.tostring(root, encoding='unicode'))
    deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
    definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
    instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
    path = '/diagnosis-api/instances/' + instance + '/review'
    for node in ('Voltage', 'VoltageConclusion', 'Reseat'):
        state = wait_review(path, node)
        if node == 'Voltage':
            assert state['instructions']['assessment'] == '长文本 / Long instructions ' * 1000
        post(path, {'action': 'confirm', 'taskId': state['taskId'],
                    'next': 'V_solved' if node == 'Reseat' and not handoff else None})
    assert engine_request('/process-api/history/historic-process-instances/' + instance).get('endTime')
print('PASS: worker-free manual branches, terminal handoff and long deployed instructions')
