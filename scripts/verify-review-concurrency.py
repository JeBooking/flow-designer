"""随机端口和内存库验证并发复核的审计、失败记录及重复动作核验。"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f, compile_workflow, deploy, engine_request
from python_sessions import stop_process
from verification_fixtures import post, wait_for, historic_values, ended


def workflow(actions):
    root = ET.Element(b('definitions'), {'targetNamespace': 'concurrent-review-verification'})
    process = ET.SubElement(root, b('process'), {'id': 'ConcurrentActions' if actions else 'ConcurrentFailures'})
    ET.SubElement(process, b('startEvent'), {'id': 'Start'})

    def investigation(name):
        ET.SubElement(process, b('task'), {'id': name, f('diagnosisKind'): 'investigation',
            f('humanDecision'): 'true', f('observation'): 'Simulated data',
            f('acquisition'): 'Manual verification', f('assessment'): 'Select a branch',
            f('referenceImage'): 'data:text/plain;base64,AAAA'})

    def edge(source, target, branch=None):
        fields = {'id': source + '_' + target, 'sourceRef': source, 'targetRef': target}
        if branch:
            fields[f('diagnosisBranch')] = branch
        ET.SubElement(process, b('sequenceFlow'), fields)

    investigation('Root')
    edge('Start', 'Root')
    if actions:
        ET.SubElement(process, b('task'), {'id': 'Solved', f('diagnosisKind'): 'problemSolved'})
    for index in range(8):
        name = 'Leaf' + str(index)
        if actions:
            conclusion = 'Conclusion' + str(index)
            ET.SubElement(process, b('task'), {'id': conclusion, f('diagnosisKind'): 'conclusion',
                f('detailText'): 'Observed condition'})
            ET.SubElement(process, b('task'), {'id': name, f('diagnosisKind'): 'remediation',
                f('actionMode'): 'manual', f('detailText'): 'Simulated action'})
            edge('Root', conclusion, 'yes')
            edge(conclusion, name)
            edge(name, 'Solved')
        else:
            investigation(name)
            edge('Root', name, 'yes')
    return ET.tostring(root, encoding='unicode')


def verify():
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    previous_host = os.environ.get('FLOWABLE_URL')
    os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='review-concurrency-') as directory:
        directory = Path(directory)
        with (directory / 'engine.log').open('w', encoding='utf-8') as log:
            engine = subprocess.Popen(['java', '-jar',
                str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:reviewverification;DB_CLOSE_DELAY=-1'],
                cwd=directory, stdout=log, stderr=log,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            try:
                def ready():
                    if engine.poll() is not None:
                        raise AssertionError('Verification engine exited')
                    try:
                        return engine_request('/process-api/management/engine')
                    except RuntimeError:
                        return None
                wait_for(ready)
                conflicts = 0
                for actions in (False, True):
                    bundle = compile_workflow(workflow(actions))
                    deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
                    definition = engine_request('/process-api/repository/process-definitions?deploymentId='
                        + deployment['id'])['data'][0]['id']
                    for iteration in range(12):
                        instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
                        path = '/diagnosis-api/instances/' + instance + '/review'
                        root_task = engine_request(path + '/tasks')['tasks'][0]
                        post(path, {'action': 'confirm', 'taskId': root_task['taskId'], 'next': 'yes'})
                        tasks = engine_request(path + '/tasks')['tasks']
                        assert len(tasks) == 8
                        expected = Counter({root_task['taskId']: 1})
                        for next_value in (('not_ok', 'ok') if actions else ('yes',)):
                            pending = list(tasks)
                            expected.update(task['taskId'] for task in tasks)
                            deadline = time.monotonic() + 60

                            def complete(task):
                                try:
                                    post(path, {'action': 'confirm', 'taskId': task['taskId'], 'next': next_value})
                                except RuntimeError as error:
                                    if 'HTTP 409' not in str(error):
                                        raise
                                    return task

                            while pending:
                                assert time.monotonic() < deadline, 'Concurrent review retries timed out'
                                with ThreadPoolExecutor(max_workers=8) as pool:
                                    pending = [task for task in pool.map(complete, pending) if task]
                                conflicts += len(pending)
                            if actions and next_value == 'not_ok':
                                remaining = engine_request(path + '/tasks')['tasks']
                                assert {task['taskId'] for task in remaining} == {task['taskId'] for task in tasks}
                                assert all(task['lastActionResult'] == 'not_ok' for task in remaining)
                                assert not ended(instance)
                        wait_for(lambda: ended(instance))
                        values = historic_values(instance)
                        records = values['diagnosticReviews']
                        actual = Counter(record['taskId'] for record in records)
                        assert actual == expected, {'round': iteration, 'actions': actions,
                            'missing': dict(expected - actual), 'duplicates': dict(actual - expected)}
                        assert len({record['id'] for record in records}) == len(records)
                        assert values['diagnosticStatus'] == ('problemSolved' if actions else 'failed')
                        if not actions:
                            assert len(values['diagnosticFailures']) == len(tasks)
                            assert all(record['recordVersion'] == 1 and record['source'] == 'route'
                                and record['code'] == 'route/no-outgoing' and record['executionId']
                                for record in values['diagnosticFailures'])
                            assert {record['nodeId'] for record in values['diagnosticFailures']} == {
                                task['nodeId'] for task in tasks}
                print(json.dumps({'passed': True, 'rounds': 24, 'parallelTasksPerRound': 8,
                    'optimisticConflictsRetried': conflicts,
                    'checks': ['exact audit counts', 'unique record IDs', 'end history',
                               'failure records', 'not-OK task retention', 'not-OK then OK audit']}, ensure_ascii=False))
            except BaseException:
                log.flush()
                print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-12000:])
                raise
            finally:
                stop_process(engine)
                if previous_host is None:
                    os.environ.pop('FLOWABLE_URL', None)
                else:
                    os.environ['FLOWABLE_URL'] = previous_host


if __name__ == '__main__':
    verify()
