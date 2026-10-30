"""真实 HTTP/Flowable 验证等待释放解释器、后端重启恢复与设备动作不重放。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f, engine_request
from python_sessions import stop_process
from server import create_server
from verification_fixtures import wait_for

SOURCE = '''
from pathlib import Path
import os
__diagnosis_stateless__ = True

class Reading:
    def __init__(self): self.value = 24
    def __diagnosis_checkpoint__(self): return {'value': self.value}
    @classmethod
    def __diagnosis_restore__(cls, state):
        value = cls()
        value.value = state['value']
        return value

class Device:
    def __init__(self):
        with Path('constructors.txt').open('a') as stream: stream.write('created\\n')
        self.latest = None
        self.actions = 0
    def __diagnosis_checkpoint__(self): return dict(self.__dict__)
    @classmethod
    def __diagnosis_restore__(cls, state):
        value = object.__new__(cls)
        value.__dict__.update(state)
        return value
    def ready(self): return True
    def collect(self):
        self.latest = Reading()
        return self.latest
    def check(self, reading): return {'same': reading is self.latest, 'pid': os.getpid()}
    def action(self):
        self.actions += 1
        with Path('actions.txt').open('a') as stream: stream.write('action\\n')
    def verify(self, reading):
        assert reading is self.latest
        return {'same': True, 'actions': self.actions, 'pid': os.getpid()}
'''


def workflow():
    root = ET.Element(b('definitions'), {'targetNamespace': 'checkpoint-recovery'})
    process = ET.SubElement(root, b('process'), {'id': 'CheckpointRecovery'})
    ET.SubElement(process, b('startEvent'), {'id': 'Start'})
    for name, kind, function in [('Ready', 'investigation', 'ready'),
        ('Read', 'investigationAction', 'collect'), ('Check', 'investigation', 'check'),
        ('Conclusion', 'conclusion', None), ('Action', 'remediation', 'action'),
        ('Verify', 'deepDiagnosis', 'verify'), ('Solved', 'problemSolved', None)]:
        fields = {'id': name, f('diagnosisKind'): kind, f('detailText'): name}
        if function:
            fields.update({f('pythonModule'): 'recovery_fixture', f('pythonFactory'): 'Device', f('pythonFunction'): function})
        if name in ('Check', 'Verify'):
            fields[f('pythonArguments')] = '{"reading":"$Read"}'
        if name == 'Check':
            fields[f('humanDecision')] = 'true'
        if kind == 'investigation':
            fields.update({f('observation'): 'Reading', f('acquisition'): 'Simulated device',
                f('assessment'): 'Compare native identity', f('referenceImage'): 'data:text/plain;base64,AAAA'})
        ET.SubElement(process, b('task'), fields)
    chain = ['Start', 'Ready', 'Read', 'Check', 'Conclusion', 'Action', 'Verify', 'Solved']
    for source, target in zip(chain, chain[1:]):
        fields = {'id': source + target, 'sourceRef': source, 'targetRef': target}
        if source in ('Ready', 'Check'):
            fields[f('diagnosisBranch')] = 'yes'
        ET.SubElement(process, b('sequenceFlow'), fields)
    return ET.tostring(root, encoding='unicode')


def verify():
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    previous = os.environ.get('FLOWABLE_URL')
    os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='execution-recovery-') as directory:
        directory = Path(directory)
        (directory / 'recovery_fixture.py').write_text(SOURCE, encoding='utf-8')
        with (directory / 'engine.log').open('w', encoding='utf-8') as log:
            engine = subprocess.Popen(['java', '-jar', str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:executionrecovery;DB_CLOSE_DELAY=-1'],
                cwd=directory, stdout=log, stderr=log,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            server = thread = None
            try:
                def ready():
                    try:
                        return engine_request('/process-api/management/engine')
                    except RuntimeError:
                        return None
                wait_for(ready)

                def open_server():
                    value = create_server(0, registry_file=directory / 'registry.json', recover=True)
                    value.RequestHandlerClass.log_message = lambda *args: None
                    serving = threading.Thread(target=value.serve_forever, daemon=True)
                    serving.start()
                    return value, serving

                server, thread = open_server()
                def request(path, value=None):
                    data = json.dumps(value).encode() if value is not None else None
                    with urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/' + path, data,
                        {'Content-Type': 'application/json'}), timeout=70) as response:
                        return json.load(response)

                registered = request('projects', {'path': str(directory), 'python': sys.executable,
                    'module': 'recovery_fixture', 'factory': 'Device'})
                assert registered['ok']
                started = request('flowable/start', {'xml': workflow(), 'variables': {}})
                instance = started['run']['id']
                path = 'flowable/history/' + instance
                def pending():
                    state = request(path)
                    return state if state['pendingReviews'] else None
                first = wait_for(pending)
                task = first['pendingReviews'][0]
                assert task['nodeId'] == 'Check' and task['evidence']['same']
                old_pid = task['evidence']['pid']
                def released():
                    result = subprocess.run(['node', '-e',
                        'try { process.kill(Number(process.argv[1]), 0); process.exit(0) } catch { process.exit(1) }', str(old_pid)],
                        capture_output=True)
                    return result.returncode != 0
                wait_for(released)
                assert (directory / 'constructors.txt').read_text().splitlines() == ['created']
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                server, thread = open_server()
                restored = wait_for(pending)
                assert restored['pendingReviews'][0]['taskId'] == task['taskId']
                request('flowable/review/' + instance, {'action': 'confirm', 'taskId': task['taskId'], 'next': 'yes'})
                final = wait_for(lambda: (state if (state := request(path))['process']['endTime'] else None))
                values = {row['variable']['name']: row['variable']['value'] for row in final['variables']['data']}
                assert values['Verify']['same'] and values['Verify']['actions'] == 1
                assert values['Verify']['pid'] != old_pid
                assert (directory / 'constructors.txt').read_text().splitlines() == ['created']
                assert (directory / 'actions.txt').read_text().splitlines() == ['action']
                assert any(value.get('recoverable') is True for key, value in values.items() if key.startswith('pythonCheckpoint_'))
                print('PASS: real Flowable wait releases business interpreter; backend restart recovers workers, task and native identity without reconstructing or repeating actions')
            except BaseException:
                log.flush()
                print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-10000:])
                raise
            finally:
                if server:
                    server.shutdown()
                    server.server_close()
                if thread:
                    thread.join(timeout=5)
                stop_process(engine)
                if previous is None:
                    os.environ.pop('FLOWABLE_URL', None)
                else:
                    os.environ['FLOWABLE_URL'] = previous


if __name__ == '__main__':
    verify()
