"""验证当前分组协议的编译拒绝、官方 worker、人工等待和异常死信。"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f, compile_workflow, engine_request
from verification_fixtures import review_workflow, deployed_workflow, post, wait_for, review, choose, ended, historic_values

xml = review_workflow('FlowableVerification', 'verification_api', 'inspect')
bundle = compile_workflow(xml)
assert len(json.loads(bundle['files']['bindings.json'])['bindings']) == 3
for change, expected in [
    (lambda p: p.find(b('task')).set(f('pythonArguments'), '[]'), 'Arguments must be an object'),
    (lambda p: p.find(b('task')).set(f('pythonFunction'), 'invalid()'), 'Invalid Python interface'),
    (lambda p: p.find(b('task')).set(f('assessment'), ''), 'Missing required diagnostic content'),
    (lambda p: p.find(b('sequenceFlow')).set('targetRef', 'Repair'), 'Diagnostic connection violates rules'),
]:
    root = ET.fromstring(xml)
    change(root.find(b('process')))
    try:
        compile_workflow(ET.tostring(root, encoding='unicode'))
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError('Invalid workflow accepted')
if '--unit-only' in sys.argv:
    print('PASS: current workflow compilation and invalid inputs')
    sys.exit(0)

source = "def inspect(scenario='yes'): return {'next': scenario, 'samples': [21, 22]}\n"
with deployed_workflow(xml, {'verification_api.py': source}) as definition:
    for scenario in ('yes', 'no', 'invalid'):
        instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
            'variables': [{'name': 'scenario', 'type': 'string', 'value': scenario}]})['id']
        if scenario == 'invalid':
            failures = wait_for(lambda: engine_request('/process-api/management/deadletter-jobs?processInstanceId=' + instance)['data'])
            assert 'must return yes/no' in failures[0]['exceptionMessage']
            assert not review(instance) and not ended(instance)
            continue
        task = wait_for(lambda: review(instance))
        assert task['nodeId'] == ('Repair' if scenario == 'yes' else 'Escalation'), task
        choose(instance, task, **({'next': 'ok'} if scenario == 'yes' else {}))
        wait_for(lambda: ended(instance))
        values = historic_values(instance)
        assert values['Inspect']['samples'] == [21, 22]
        assert values['diagnosticStatus'] == ('problemSolved' if scenario == 'yes' else 'escalation')
        assert any(key.startswith('executionTrace_') for key in values)
print('PASS: compilation, actual Python worker, yes/no routing, action/escalation waits, history and invalid-result deadletter')
