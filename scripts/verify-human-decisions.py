"""纯人工诊断的路径子集、回退、无效提交和动作核验回归。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from verification_fixtures import review_workflow, deployed_workflow, post, wait_for, review, choose, ended, historic_values

with deployed_workflow(review_workflow('HumanReviewVerification')) as definition:
    instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
    first = wait_for(lambda: review(instance))
    assert first['nodeId'] == 'Inspect' and first['candidates'] == []
    for fields in [{'next': 'unknown'}, {'next': 'yes', 'selectedFlowIds': []},
                   {'next': 'yes', 'selectedFlowIds': ['No']},
                   {'next': 'yes', 'selectedFlowIds': ['Yes', 'Yes']},
                   {'action': 'recheck', 'targetNodeId': 'Repair', 'reason': 'Unvisited'}]:
        try:
            choose(instance, first, **fields)
        except RuntimeError as error:
            assert 'HTTP 400' in str(error)
        else:
            raise AssertionError('Invalid review accepted: ' + str(fields))
        assert review(instance)['taskId'] == first['taskId']
    choose(instance, first, next='yes', selectedFlowIds=['Yes'])
    action = wait_for(lambda: review(instance))
    assert action['nodeId'] == 'Repair'
    choose(instance, action, action='recheck', targetNodeId='Inspect', reason='Recheck evidence')
    repeated = wait_for(lambda: review(instance))
    assert repeated['nodeId'] == 'Inspect' and repeated['taskId'] != first['taskId']
    try:
        choose(instance, first, next='yes')
    except RuntimeError as error:
        assert 'HTTP 409' in str(error)
    else:
        raise AssertionError('Stale task accepted')
    choose(instance, repeated, next='yes')
    action = wait_for(lambda: review(instance))
    choose(instance, action, next='not_ok')
    assert review(instance)['taskId'] == action['taskId'] and not ended(instance)
    assert review(instance)['lastActionResult'] == 'not_ok'
    choose(instance, action, next='ok')
    wait_for(lambda: ended(instance))
    records = historic_values(instance)['diagnosticReviews']
    assert len(records) == 5 and records[-2]['actionResult'] == 'not_ok'
    assert records[-1]['actionResult'] == 'ok'
print('PASS: worker-free manual decisions, route subsets, recheck, stale/invalid rejection and repeated action audit')
