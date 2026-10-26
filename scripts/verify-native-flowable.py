"""真实 Java 引擎验证原生对象、独立会话、人工等待及异常展示。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f, compile_workflow, deploy, engine_request
from server import create_server


def post(path, value):
    return engine_request(path, json.dumps(value).encode())


def wait(check):
    for _ in range(240):
        result = check()
        if result:
            return result
        time.sleep(0.15)
    raise AssertionError('Engine state timed out')


def workflow(mode, factory='Device'):
    root = ET.Element(b('definitions'), {'targetNamespace': 'native-python-check'})
    process = ET.SubElement(root, b('process'), {'id': 'NativePython', f('diagnosisMode'): mode})
    ET.SubElement(process, b('startEvent'), {'id': 'Start'})
    image = 'data:text/plain;base64,TmF0aXZlIFB5dGhvbg=='
    def node(node_id, kind, function=None, manual=False):
        props = {'id': node_id, f('diagnosisKind'): kind, f('detailText'): node_id}
        if kind == 'investigation':
            props.update({f('observation'): 'Reading', f('acquisition'): 'Native session',
                          f('assessment'): 'Python bool', f('referenceImage'): image})
        if function:
            props.update({f('pythonModule'): 'session_fixture', f('pythonFactory'): factory,
                          f('pythonFunction'): function})
        if manual:
            props[f('humanDecision')] = 'true'
        ET.SubElement(process, b('task'), props)
    def edge(source, target, branch=None):
        props = {'id': source + '_' + target, 'sourceRef': source, 'targetRef': target}
        if branch:
            props[f('diagnosisBranch')] = branch
        ET.SubElement(process, b('sequenceFlow'), props)
    node('Ready', 'investigation', 'ready')
    node('reading', 'investigationAction', 'collect')
    node('Check', 'investigation', 'is_low', True)
    node('Conclusion', 'conclusion')
    node('Restore', 'remediation', 'restore')
    node('Verify', 'remediation', 'verify')
    node('Solved', 'problemSolved')
    edge('Start', 'Ready')
    edge('Ready', 'reading', 'yes')
    edge('reading', 'Check')
    edge('Check', 'Conclusion', 'yes')
    edge('Conclusion', 'Restore')
    edge('Restore', 'Verify')
    edge('Verify', 'Solved')
    return ET.tostring(root, encoding='unicode')


SOURCE = '''
import asyncio
from dataclasses import dataclass

@dataclass
class Reading:
    device: str
    voltage: float

class Device:
    def __init__(self, device_id, fail=False):
        self.device_id = device_id
        self.fail = fail
        self.fixed = False
        self.reading = None
        self.calls = 0

    def ready(self):
        return True

    def collect(self):
        self.reading = Reading(self.device_id, 22.6)
        return self.reading

    def is_low(self, reading):
        assert reading is self.reading
        assert reading.device == self.device_id
        return reading.voltage < 24

    def restore(self):
        if self.fail:
            raise ValueError('native engine sentinel ' + self.device_id)
        self.fixed = True
        self.calls += 1

    async def verify(self):
        await asyncio.sleep(0)
        assert self.fixed and self.calls == 1
        return {'device': self.device_id, 'fixed': self.fixed, 'calls': self.calls}

class OtherDevice(Device):
    pass
'''


with socket.socket() as available:
    available.bind(('127.0.0.1', 0))
    port = available.getsockname()[1]
os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
with tempfile.TemporaryDirectory(prefix='native-flowable-') as temporary:
    directory = Path(temporary)
    (directory / 'session_fixture.py').write_text(SOURCE, encoding='utf-8')
    registry = directory / 'registry.json'
    registry.write_text(json.dumps({'project': {'path': str(directory), 'python': sys.executable,
                        'module': 'session_fixture', 'factory': 'Device'}}), encoding='utf-8')
    with (directory / 'engine.log').open('w', encoding='utf-8') as log:
        engine = subprocess.Popen(['java', '-jar', str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
            f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:nativepython;DB_CLOSE_DELAY=-1'],
            cwd=directory, stdout=log, stderr=log)
        workers = []
        try:
            def ready():
                if engine.poll() is not None:
                    raise AssertionError('Engine exited')
                try:
                    return engine_request('/process-api/management/engine')
                except RuntimeError:
                    return False
            wait(ready)
            def deploy_mode(mode):
                bundle = compile_workflow(workflow(mode))
                changed = compile_workflow(workflow(mode, 'OtherDevice'))
                assert json.loads(bundle['files']['bindings.json'])['version'] != json.loads(changed['files']['bindings.json'])['version']
                filename = directory / (mode + '.json')
                filename.write_text(bundle['files']['bindings.json'], encoding='utf-8')
                workers.append(subprocess.Popen([sys.executable, '-u', str(ROOT / 'backend/flowable_worker.py'),
                    str(filename), '--registry', str(registry)], cwd=directory, stdout=log, stderr=log))
                deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
                return engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
            def start(definition, device, fail=False):
                return post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                    'variables': [{'name': 'device_id', 'type': 'string', 'value': device},
                                  {'name': 'fail', 'type': 'boolean', 'value': fail}]})['id']
            def values(run_id):
                return {entry['variable']['name']: entry['variable']['value'] for entry in
                    engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=1000')['data']}
            def pending(run_id):
                result = engine_request('/diagnosis-api/instances/' + run_id + '/review')
                return result if result.get('pending') else None
            for mode in ('serial', 'parallel'):
                definition = deploy_mode(mode)
                runs = [start(definition, name) for name in ('M01', 'M02')]
                markers = []
                for run_id in runs:
                    review = wait(lambda: pending(run_id))
                    before = values(run_id)
                    assert before['reading']['native'] and before['reading']['pythonType'].endswith('.Reading'), before
                    assert before['Check'] is True
                    markers.append(next(value for key, value in before.items() if key.startswith('pythonSession_')))
                    post('/diagnosis-api/instances/' + run_id + '/review', {'action': 'confirm',
                         'taskId': review['taskId'], 'next': 'yes'})
                assert markers[0] != markers[1]
                for run_id, name in zip(runs, ('M01', 'M02')):
                    wait(lambda: engine_request('/process-api/history/historic-process-instances/' + run_id).get('endTime'))
                    after = values(run_id)
                    assert after['Restore'] is None
                    assert after['Verify'] == {'device': name, 'fixed': True, 'calls': 1}, after
                print('PASS: real Flowable ' + mode + ', native Reading identity, human wait, None/async, two-run isolation', flush=True)
            failed = start(definition, 'BROKEN', True)
            review = wait(lambda: pending(failed))
            post('/diagnosis-api/instances/' + failed + '/review', {'action': 'confirm',
                 'taskId': review['taskId'], 'next': 'yes'})
            failures = wait(lambda: engine_request('/process-api/management/deadletter-jobs?processInstanceId=' + failed)['data'])
            assert 'native engine sentinel BROKEN' in failures[0]['exceptionMessage'], failures
            stack = engine_request('/process-api/management/deadletter-jobs/' + failures[0]['id'] + '/exception-stacktrace', as_text=True)
            assert 'in restore' in stack and 'ValueError: native engine sentinel BROKEN' in stack, stack
            proxy = create_server(0, registry_file=directory / 'proxy-registry.json')
            proxy.RequestHandlerClass.log_message = lambda *args: None
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()
            try:
                with urlopen(f'http://127.0.0.1:{proxy.server_port}/api/flowable/history/{failed}') as response:
                    history = json.load(response)
                assert history['failures'][0]['traceback'] == stack
            finally:
                proxy.shutdown()
                proxy.server_close()
                proxy_thread.join(timeout=5)
            print('PASS: actual deadletter task retains node error and original Python traceback', flush=True)
            missing = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
            missing_jobs = wait(lambda: engine_request('/process-api/management/deadletter-jobs?processInstanceId=' + missing)['data'])
            assert 'device_id' in missing_jobs[0]['exceptionMessage']
            assert any(key.startswith('pythonSession_') for key in values(missing))
            print('PASS: first-node initialization failure records its session before executing Python', flush=True)
        except Exception:
            print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-18000:])
            raise
        finally:
            for worker in workers:
                worker.terminate()
                worker.wait(timeout=10)
            engine.terminate()
            engine.wait(timeout=10)
