"""真实回退保留执行依据，变量覆盖与任务状态在同一事务中更新。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from verification_fixtures import review_workflow, deployed_workflow, post, wait_for, review, choose, ended, historic_values

xml = review_workflow('DiagnosticRecheckVerification', 'recheck_fixture', 'inspect')
source = "def inspect(scenario='yes'): return {'next': scenario, 'data': [21, 22]}\n"
with deployed_workflow(xml, {'recheck_fixture.py': source}) as definition:
    instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
        'variables': [{'name': 'scenario', 'type': 'string', 'value': 'yes'}]})['id']
    first = wait_for(lambda: review(instance))
    assert first['nodeId'] == 'Repair'
    for fields in [{'targetNodeId': 'Inspect', 'reason': ''},
                   {'targetNodeId': 'Inspect', 'reason': 'Invalid override', 'variables': {'Inspect': {}}}]:
        try:
            choose(instance, first, action='recheck', **fields)
        except RuntimeError as error:
            assert 'HTTP 400' in str(error)
        else:
            raise AssertionError('Invalid recheck accepted')
    choose(instance, first, action='recheck', targetNodeId='Inspect', reason='Changed input', variables={'scenario': 'no'})
    escalation = wait_for(lambda: review(instance))
    assert escalation['nodeId'] == 'Escalation'
    values = historic_values(instance)
    record = values['diagnosticReviews'][0]
    assert record['previousInputs']['scenario'] == 'yes'
    assert record['inputChanges']['scenario'] == 'no'
    assert record['clearedResults']['Inspect']['next'] == 'yes'
    assert 'Inspect' in {entry['id'] for entry in escalation['candidates']}
    choose(instance, escalation)
    wait_for(lambda: ended(instance))
    assert len(historic_values(instance)['diagnosticReviews']) == 2
    try:
        choose(instance, escalation, action='recheck', targetNodeId='Inspect', reason='Too late')
    except RuntimeError as error:
        assert 'HTTP 409' in str(error)
    else:
        raise AssertionError('Ended instance accepted a recheck')
print('PASS: validated recheck, frozen previous results/inputs, new route, end history and ended-instance rejection')
