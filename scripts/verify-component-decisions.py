"""真实 worker 验证组件主动等待、原始依据、回退与重新判断。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from verification_fixtures import review_workflow, deployed_workflow, post, wait_for, review, choose, ended, historic_values

xml = review_workflow('ComponentReviewVerification', 'component_fixture', 'inspect')
source = "from diagnostic_components import DecisionComponent\ndef inspect(): return DecisionComponent().run({'samples': [21, 22]}, instructions='Check samples')\n"
with deployed_workflow(xml, {'component_fixture.py': source}) as definition:
    instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
    first = wait_for(lambda: review(instance))
    assert first['nodeId'] == 'Inspect' and first['mode'] == 'decision'
    assert first['evidence']['samples'] == [21, 22]
    assert first['instructions']['assessment'] == 'Check samples'
    choose(instance, first, next='yes')
    action = wait_for(lambda: review(instance))
    assert action['nodeId'] == 'Repair'
    choose(instance, action, action='recheck', targetNodeId='Inspect', reason='Repeat acquisition')
    repeated = wait_for(lambda: review(instance))
    assert repeated['nodeId'] == 'Inspect' and repeated['taskId'] != first['taskId']
    choose(instance, repeated, next='no')
    escalation = wait_for(lambda: review(instance))
    assert escalation['nodeId'] == 'Escalation'
    choose(instance, escalation)
    wait_for(lambda: ended(instance))
    records = historic_values(instance)['diagnosticReviews']
    assert len(records) == 4 and sum(record['action'] == 'recheck' for record in records) == 1
print('PASS: component-requested judgment without flags, evidence, recheck and historic audit')
