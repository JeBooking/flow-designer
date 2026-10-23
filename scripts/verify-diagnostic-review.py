"""验证等待复核、真实回退、旧结果隔离、重复复核与最终确认。"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, deploy, engine_request


def post(path, body):
    return engine_request(path, json.dumps(body).encode())


def wait_review(run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        review = engine_request('/diagnosis-api/instances/' + run_id + '/review')
        if review['pending']:
            assert not engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime')
            return review
        time.sleep(0.2)
    raise AssertionError('Escalation did not pause for review')


def wait_end(run_id):
    deadline = time.monotonic() + 30
    while not engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime'):
        assert time.monotonic() < deadline, 'Rechecked process did not finish'
        time.sleep(0.2)


def variables(run_id):
    rows = engine_request('/process-api/runtime/process-instances/' + run_id + '/variables')
    return {row['name']: row['value'] for row in rows}


with tempfile.TemporaryDirectory(prefix='diagnostic-review-') as temp:
    xml = (ROOT / 'src/views/ProcessDesigner/examples/sensor-comparison.bpmn').read_text(encoding='utf-8')
    compiled = compile_workflow(xml)
    bindings_file = Path(temp) / 'bindings.json'
    bindings_file.write_text(compiled['files']['bindings.json'], encoding='utf-8')
    log_path = ROOT / 'backend/.local/diagnostic-review-smoke.log'
    with log_path.open('w', encoding='utf-8') as log:
        worker = subprocess.Popen([sys.executable, '-X', 'utf8', str(ROOT / 'backend/flowable_worker.py'),
            str(bindings_file), '--project', str(ROOT / 'backend/examples/diagnostic_demo')], stdout=log, stderr=log)
        try:
            deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
            definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
            run_id = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                'variables': [{'name': 'scenario', 'type': 'string', 'value': 'severe'}]})['id']
            review = wait_review(run_id)
            candidates = {item['id'] for item in review['candidates']}
            assert candidates == {'ReadSensors', 'SensorA'}, candidates
            assert variables(run_id)['SensorConclusion']['channel'] == 'A'
            path = '/diagnosis-api/instances/' + run_id + '/review'
            for invalid in [dict(targetNodeId='SensorB', reason='Unvisited target'),
                            dict(targetNodeId='ReadSensors', reason=''),
                            dict(targetNodeId='ReadSensors', reason='Invalid override', variables={'Calibrate': {}}),
                            dict(targetNodeId='ReadSensors', reason='Stale review', taskId='old-task')]:
                try:
                    post(path, {'action': 'recheck', 'taskId': review['taskId'], **invalid})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Invalid review request was accepted')
                assert engine_request(path)['taskId'] == review['taskId']
                assert variables(run_id)['SensorConclusion']['channel'] == 'A'
            # 首次回退仍判严重异常，确认可以连续进行复核。
            post(path, {'action': 'recheck', 'taskId': review['taskId'], 'targetNodeId': 'ReadSensors',
                        'reason': 'Reacquire to verify suspected sensor A'})
            second = wait_review(run_id)
            assert second['taskId'] != review['taskId']
            audit = variables(run_id)['diagnosticReviews']
            assert len(audit) == 1 and audit[0]['clearedResults']['SensorConclusion']['channel'] == 'A'
            # 第二次回退更换采样场景，验证旧 A 支路结果不会污染新 B 支路结论。
            post(path, {'action': 'recheck', 'taskId': second['taskId'], 'targetNodeId': 'ReadSensors',
                        'reason': 'New measurements indicate sensor B', 'variables': {'scenario': 'sensor-b'}})
            wait_end(run_id)
            rows = engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=100')['data']
            final = {row['variable']['name']: row['variable']['value'] for row in rows}
            assert final['SensorConclusion']['channel'] == 'B', final['SensorConclusion']
            assert 'SensorA' not in final
            assert len(final['diagnosticReviews']) == 2
            assert final['diagnosticReviews'][1]['previousInputs']['scenario'] == 'severe'
            activities = engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&size=200')['data']
            assert sum(item['activityId'] == 'ReadSensors' for item in activities) == 3
            assert sum(item['activityId'] == 'Solved' for item in activities) == 1
            print('PASS: escalation waits; invalid/stale review requests rejected; two rechecks preserve snapshots and isolate A/B results', flush=True)
            partial_id = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                'variables': [{'name': 'scenario', 'type': 'string', 'value': 'severe'}]})['id']
            partial = wait_review(partial_id)
            original_chart = variables(partial_id)['ReadSensors']['chart']
            post('/diagnosis-api/instances/' + partial_id + '/review', {'action': 'recheck', 'taskId': partial['taskId'],
                'targetNodeId': 'SensorA', 'reason': 'Re-evaluate sensor A only', 'variables': {'scenario': 'normal'}})
            wait_end(partial_id)
            rows = engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + partial_id + '&size=100')['data']
            partial_values = {row['variable']['name']: row['variable']['value'] for row in rows}
            assert partial_values['ReadSensors']['chart'] == original_chart
            assert 'ReadSensors' not in partial_values['diagnosticReviews'][0]['clearedResults']
            assert 'SensorA' in partial_values['diagnosticReviews'][0]['clearedResults']
            print('PASS: selective recheck preserves upstream acquisition and clears downstream results', flush=True)
            # 新实例确认上升才真正结束。
            confirmed_id = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                'variables': [{'name': 'scenario', 'type': 'string', 'value': 'severe'}]})['id']
            pending = wait_review(confirmed_id)
            post('/diagnosis-api/instances/' + confirmed_id + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'reason': 'Specialist required'})
            wait_end(confirmed_id)
            try:
                post('/diagnosis-api/instances/' + confirmed_id + '/review', {'action': 'recheck', 'taskId': pending['taskId'], 'targetNodeId': 'ReadSensors', 'reason': 'Too late'})
            except RuntimeError:
                pass
            else:
                raise AssertionError('Completed process accepted a recheck')
            print('PASS: explicit escalation confirmation completes the instance; ended instances reject rechecks', flush=True)
        finally:
            worker.terminate()
            worker.wait(timeout=10)
