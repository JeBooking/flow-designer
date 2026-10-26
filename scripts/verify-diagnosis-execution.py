"""在随机端口/内存库验证真实引擎的串行恢复与并行失败隔离。"""
import json
import base64
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, deploy, engine_request, b, f, BPMN, FLOWABLE


def post(path, data):
    return engine_request(path, json.dumps(data).encode())


def wait_for(callback):
    for _ in range(150):
        value = callback()
        if value:
            return value
        time.sleep(0.15)
    raise AssertionError('Timed out waiting for engine state')


def workflow(mode, all_failed=False, manual=False, unmatched=False, reference=None):
    root = ET.Element(b('definitions'), {'targetNamespace': 'diagnosis-execution-check'})
    process = ET.SubElement(root, b('process'), {'id': 'ExecutionModes', f('diagnosisMode'): mode})
    ET.SubElement(process, b('startEvent'), {'id': 'Start'})
    image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII='
    def node(node_id, kind, **fields):
        props = {'id': node_id, f('diagnosisKind'): kind}
        props.update({f(key): value for key, value in fields.items()})
        if kind == 'investigation':
            props.update({f('observation'): 'Observe', f('acquisition'): 'Acquire',
                f('assessment'): 'Assess', f('referenceImage'): image})
        if kind in ('investigation', 'remediation'):
            props.update({f('pythonModule'): 'execution_fixture',
                f('pythonFunction'): 'yes' if kind == 'investigation' else 'noop'})
        ET.SubElement(process, b('task'), props)
    def flow(source, target, branch=None, order=None):
        props = {'id': source + '_' + target, 'sourceRef': source, 'targetRef': target}
        if branch: props[f('diagnosisBranch')] = branch
        if order is not None: props[f('diagnosisOrder')] = str(order)
        ET.SubElement(process, b('sequenceFlow'), props)
    node('Root', 'investigation')
    node('Fail', 'investigation')
    node('Good1', 'investigation')
    node('Good2', 'investigation')
    flow('Start', 'Root')
    # XML 首条不是优先级最高；同优先级则依次保留 XML 中的顺序。
    flow('Root', 'Good1', 'yes', 0)
    flow('Root', 'Fail', 'yes', -5)
    flow('Root', 'Good2', 'yes', 0)
    if not all_failed:
        for suffix in ('1', '2'):
            node('Conclusion' + suffix, 'conclusion', detailText='Conclusion detail')
            node('Repair' + suffix, 'remediation', detailText='Repair detail')
            flow('Good' + suffix, 'Conclusion' + suffix, 'yes')
            flow('Conclusion' + suffix, 'Repair' + suffix)
            flow('Repair' + suffix, 'Solved')
        node('Solved', 'problemSolved', detailText='Resolved detail')
    if unmatched:
        flow('Fail', 'Good1', 'no')
    if manual:
        root_node = next(element for element in process if element.get('id') == 'Root')
        root_node.set(f('humanDecision'), 'true')
        root_node.attrib.pop(f('pythonModule'))
        root_node.attrib.pop(f('pythonFunction'))
    if reference:
        root_node = next(element for element in process if element.get('id') == 'Root')
        root_node.set(f('referenceImage'), reference)
        root_node.set(f('referenceImageName'), 'manual.pdf')
    return ET.tostring(root, encoding='unicode')


with socket.socket() as available:
    available.bind(('127.0.0.1', 0))
    port = available.getsockname()[1]
os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
with tempfile.TemporaryDirectory(prefix='diagnosis-modes-') as directory:
    directory = Path(directory)
    (directory / 'execution_fixture.py').write_text('def yes(): return True\ndef noop(): pass\n')
    with (directory / 'engine.log').open('w', encoding='utf-8') as log:
        engine = subprocess.Popen(['java', '-jar', str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
            f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:executionmodes;DB_CLOSE_DELAY=-1'],
            cwd=directory, stdout=log, stderr=log)
        workers = []
        launched_versions = set()
        try:
            def ready():
                if engine.poll() is not None: raise RuntimeError((directory / 'engine.log').read_text(errors='replace'))
                try: return engine_request('/process-api/management/engine')
                except RuntimeError: return False
            wait_for(ready)
            def launch(mode, all_failed=False, manual=False, unmatched=False, reference=None):
                bundle = compile_workflow(workflow(mode, all_failed, manual, unmatched, reference))
                metadata = json.loads(bundle['files']['bindings.json'])
                filename = directory / (metadata['version'] + '.json')
                filename.write_text(bundle['files']['bindings.json'], encoding='utf-8')
                # 多次排查由同一个协调器管理独立会话，不能重复订阅同一执行包的主题。
                if metadata['version'] not in launched_versions:
                    launched_versions.add(metadata['version'])
                    workers.append(subprocess.Popen([str(ROOT / 'backend/.local/venv/Scripts/python.exe'), '-X', 'utf8',
                        str(ROOT / 'backend/flowable_worker.py'), str(filename), '--project', str(directory)],
                        cwd=directory, stdout=log, stderr=log))
                deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
                definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
                return post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
            def variables(instance):
                return {entry['variable']['name']: entry['variable']['value'] for entry in
                    engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + instance + '&size=1000')['data']}
            def activities(instance):
                return engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + instance + '&size=1000')['data']
            def finished(instance):
                return engine_request('/process-api/history/historic-process-instances/' + instance).get('endTime')
            def review(instance):
                value = engine_request('/diagnosis-api/instances/' + instance + '/review')
                return value if value.get('pending') else None
            serial = launch('serial')
            pending = wait_for(lambda: review(serial))
            assert pending['mode'] == 'success' and {o['id'] for o in pending['options']} == {'continue', 'finish'}, pending
            state = variables(serial)
            assert state['diagnosticStatus'] == 'paused', state
            assert [item['node'] for item in state['diagnosticQueue']] == ['Good2'], state
            assert state['diagnosticFailures'][0]['node'] == 'Fail', state
            assert state['diagnosticFailures'][0]['path'] == ['Root', 'Fail'], state
            assert not any(visit['activityId'] == 'Good2' for visit in activities(serial))
            post('/diagnosis-api/instances/' + serial + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'continue'})
            wait_for(lambda: finished(serial))
            assert variables(serial)['diagnosticStatus'] == 'problemSolved'
            visits = activities(serial)
            assert sum(visit['activityId'] == 'Root' for visit in visits) == 1
            assert sum(visit['activityId'] == 'Good1' for visit in visits) == 1
            assert sum(visit['activityId'] == 'Good2' for visit in visits) == 1
            assert sum(visit['activityId'] == 'Solved' for visit in visits) == 2
            stop = launch('serial')
            pending = wait_for(lambda: review(stop))
            post('/diagnosis-api/instances/' + stop + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'finish'})
            wait_for(lambda: finished(stop))
            assert not any(visit['activityId'] == 'Good2' for visit in activities(stop))
            assert variables(stop)['diagnosticReviews'][0]['next'] == 'finish'
            parallel = launch('parallel')
            wait_for(lambda: finished(parallel))
            state = variables(parallel)
            assert len(state['diagnosticFailures']) == 1 and state['diagnosticFailures'][0]['node'] == 'Fail', state
            assert state['diagnosticStatus'] == 'problemSolved', state
            visits = activities(parallel)
            assert all(sum(visit['activityId'] == node for visit in visits) == 1 for node in ('Good1', 'Good2'))
            for mode in ('serial', 'parallel'):
                failed = launch(mode, True, unmatched=True)
                wait_for(lambda: finished(failed))
                state = variables(failed)
                assert state['diagnosticStatus'] == 'failed' and len(state['diagnosticFailures']) == 3, state
            manual = launch('serial', manual=True)
            pending = wait_for(lambda: review(manual))
            assert pending['mode'] == 'decision' and pending['instructions']['assessment'] == 'Assess', pending
            post('/diagnosis-api/instances/' + manual + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'yes'})
            pending = wait_for(lambda: review(manual))
            assert pending['mode'] == 'success', pending
            post('/diagnosis-api/instances/' + manual + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'finish'})
            wait_for(lambda: finished(manual))
            # 超过旧 multipart 和 JSON 字符串默认上限的参考文件仍应能部署并进入人工复核。
            reference = 'data:application/pdf;base64,' + base64.b64encode(b'%PDF-1.4\n' + b'x' * (17 * 1024 * 1024)).decode()
            large = launch('serial', manual=True, reference=reference)
            pending = wait_for(lambda: review(large))
            assert pending['instructions']['referenceImageName'] == 'manual.pdf'
            assert pending['instructions']['referenceImage'] == reference
            post('/diagnosis-api/instances/' + large + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'yes'})
            pending = wait_for(lambda: review(large))
            assert pending['mode'] == 'success'
            post('/diagnosis-api/instances/' + large + '/review', {'action': 'confirm', 'taskId': pending['taskId'], 'next': 'finish'})
            wait_for(lambda: finished(large))
            assert json.loads(compile_workflow(workflow('serial'))['files']['bindings.json'])['version'] != json.loads(compile_workflow(workflow('parallel'))['files']['bindings.json'])['version']
            print('PASS: real Flowable serial ordered/stable queue, failure continuation, success pause/continue/finish, no duplicate sibling execution, parallel failure isolation, all-failed outcomes and large PDF review metadata')
        except Exception:
            print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-18000:])
            raise
        finally:
            for worker in workers:
                worker.terminate()
                worker.wait(timeout=10)
            engine.terminate()
            engine.wait(timeout=10)
