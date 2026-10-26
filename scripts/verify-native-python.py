"""验证真实隔离子进程的原生对象、状态、并发和 HTTP 调试生命周期，无需 Java。"""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import gc
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
import venv
import weakref

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from python_sessions import PythonSession, SessionManager, project_key
from flowable_worker import make_callback, select_project
from server import create_server
from worker_lease import WorkerLease


SOURCE = '''
import asyncio
import os
from pathlib import Path
import sys
import threading
import time
from diagnostic_components import human_judgment

counter = 0
constructed = 0

class Reading:
    def __init__(self):
        self.samples = {1, 2, 3}
        self.parent = self

class Device:
    def __init__(self, serial, gain=2):
        global constructed
        constructed += 1
        Path('constructed.txt').write_text(str(constructed))
        self.serial = serial
        self.gain = gain
        self.calls = 0
        self.barrier = threading.Barrier(2)
        self.reading = None
        self.loop = None

    def status(self, label='default'):
        self.calls += 1
        return {'calls': self.calls, 'serial': self.serial, 'gain': self.gain,
                'label': label, 'constructed': constructed}

    def collect(self):
        self.reading = Reading()
        return self.reading

    def consume(self, reading):
        return {'identical': reading is self.reading,
                'samples': sorted(reading.samples), 'cycle': reading.parent is reading}

    async def async_identity(self, reading):
        await asyncio.sleep(0.01)
        loop = asyncio.get_running_loop()
        same = self.loop is None or self.loop is loop
        self.loop = loop
        return {'identical': reading is self.reading, 'sameLoop': same}

    def parallel(self, side):
        self.barrier.wait(timeout=4)
        return side

    def action(self):
        self.calls += 1

    def explode(self):
        raise ValueError('native sentinel')

    def wait_for_close(self):
        Path('waiting.txt').write_text('ready')
        time.sleep(20)

    def decide(self, reading):
        return reading is self.reading

    def manual(self, reading):
        return human_judgment(reading, 'Inspect reading', ('yes', 'no'))

def make_device(serial, gain=3) -> Device:
    return Device(serial, gain)

async def make_async_device(serial) -> Device:
    await asyncio.sleep(0)
    return Device(serial)

def increment():
    global counter
    counter += 1
    return counter

def environment():
    return {'cwd': os.getcwd(), 'prefix': sys.prefix, 'executable': sys.executable}
'''


class CallbackBuilder:
    def __init__(self):
        self.values = {}
        self.failed = False

    def success(self):
        return self

    def failure(self):
        self.failed = True
        return self

    def variable_json(self, name, value):
        self.values[name] = value
        return self

    variable_string = variable_json
    variable_boolean = variable_json

    def error_message(self, value):
        self.error = value
        return self

    def error_details(self, value):
        self.details = value
        return self

    def retries(self, value):
        self.retry_count = value
        return self


def verify():
    checks = []
    with tempfile.TemporaryDirectory(prefix='native-python-check-') as temporary:
        directory = Path(temporary)
        project_dir = directory / 'project'
        project_dir.mkdir()
        (project_dir / 'native_api.py').write_text(SOURCE, encoding='utf-8')
        project = {'path': str(project_dir), 'python': sys.executable,
                   'module': 'native_api', 'factory': 'Device'}
        sessions = SessionManager(timeout=12)
        server = create_server(0, registry_file=directory / 'registry.json', timeout=12)
        server.RequestHandlerClass.log_message = lambda *args: None
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def http(path, data):
            request = Request(f'http://127.0.0.1:{server.server_port}/api/projects' + path,
                              data=json.dumps(data).encode(),
                              headers={'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=15) as response:
                    return response.status, json.load(response)
            except HTTPError as response:
                return response.code, json.load(response)

        def call(session, function, variables=None, node=None, factory='Device', **binding):
            response = session.call({'binding': {'module': 'native_api', 'factory': factory,
                                    'function': function, 'nodeId': node or function, **binding},
                                    'variables': variables or {}})
            assert response['ok'], response
            assert response['sessionId'] == session.id, response
            return response

        def expect_error(function, text):
            try:
                function()
            except RuntimeError as error:
                assert text.lower() in str(error).lower(), error
            else:
                raise AssertionError('Expected session failure: ' + text)

        try:
            first = sessions.get('run-one', project)
            initial = call(first, 'status', {'serial': 'A'})['result']
            second = call(first, 'status', {'serial': 'IGNORED', 'gain': 99})['result']
            assert initial == {'calls': 1, 'serial': 'A', 'gain': 2,
                               'label': 'default', 'constructed': 1}, initial
            assert second == {**initial, 'calls': 2}, second
            assert sessions.get('run-one', project, first.id) is first
            checks.append('same instance, one construction, init inputs and Python defaults')

            other = sessions.get('run-two', project)
            assert call(first, 'increment', factory='')['result'] == 1
            assert call(first, 'increment', factory='')['result'] == 2
            assert call(other, 'increment', factory='')['result'] == 1
            assert call(other, 'status', {'serial': 'B'})['result']['calls'] == 1
            assert other.id != first.id
            checks.append('run isolation for instances and module globals')

            projection = call(first, 'collect', node='reading')['result']
            assert projection['native'] and projection['pythonType'].endswith('.Reading'), projection
            variables = {'reading': projection}
            consumed = call(first, 'consume', variables)['result']
            assert consumed == {'identical': True, 'samples': [1, 2, 3], 'cycle': True}, consumed
            for _ in range(2):
                assert call(first, 'async_identity', variables)['result'] == {
                    'identical': True, 'sameLoop': True}
            assert call(first, 'action')['result'] is None
            assert call(first, 'status')['result']['calls'] == 4
            checks.append('native identity and circular objects across sync/async calls, persistent loop, None action')

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(call, first, 'parallel', {'side': side},
                                       node='parallel_' + side) for side in ('left', 'right')]
                assert {future.result(timeout=8)['result'] for future in futures} == {'left', 'right'}
            checks.append('two concurrent methods enter a shared-instance barrier')

            failure = first.call({'binding': {'module': 'native_api', 'factory': 'Device',
                                  'function': 'explode'}, 'variables': {}})
            assert not failure['ok'] and failure['error'] == 'ValueError: native sentinel', failure
            assert 'native_api.py' in failure['traceback'] and 'in explode' in failure['traceback'], failure
            assert "raise ValueError('native sentinel')" in failure['traceback'], failure
            assert call(first, 'decide', variables, kind='investigation')['route'] == 'yes'
            manual = call(first, 'manual', variables, kind='investigation', outgoing=['yes', 'no'])
            assert manual['human'] and manual['result'] == projection, manual
            assert manual['request']['instructions'] == 'Inspect reading', manual
            checks.append('original exception traceback, automatic branch and native human judgment projection')

            for factory, gain in [('make_device', 3), ('make_async_device', 2)]:
                created = call(first, 'status', {'serial': factory}, factory=factory)['result']
                assert created['serial'] == factory and created['gain'] == gain, created
                assert call(first, 'status', factory=factory)['result']['calls'] == 2
            checks.append('function and async factories construct once with required inputs and defaults')

            # 删除业务构造痕迹后发现类接口，确认发现阶段没有执行构造器。
            (project_dir / 'constructed.txt').unlink()
            status, registered = http('', project)
            assert status == 200, registered
            assert not (project_dir / 'constructed.txt').exists()
            assert {item['name'] for item in registered['initParameters']} == {'serial', 'gain'}, registered
            project_id = registered['project']['id']
            assert 'collect' in {item['name'] for item in registered['interfaces']}
            status, missing = http('/' + project_id + '/call', {'function': 'status'})
            assert status == 422 and 'serial' in missing['traceback'], missing
            status, debug = http('/' + project_id + '/call', {
                'function': 'status', 'inputs': {'serial': 'debug', 'gain': 7},
                'sessionId': missing['sessionId']})
            assert status == 200 and debug['result']['serial'] == 'debug', debug
            debug_id = debug['sessionId']
            status, debug = http('/' + project_id + '/call', {
                'function': 'status', 'sessionId': debug_id})
            assert status == 200 and debug['result']['calls'] == 2, debug
            assert http('/' + project_id + '/sessions/close', {'sessionId': debug_id})[0] == 200
            assert http('/' + project_id + '/call', {'function': 'status', 'sessionId': debug_id})[0] == 400
            status, reset = http('/' + project_id + '/call', {
                'function': 'status', 'inputs': {'serial': 'reset'}})
            assert status == 200 and reset['sessionId'] != debug_id, reset
            assert reset['result']['calls'] == 1 and reset['result']['serial'] == 'reset', reset
            checks.append('HTTP class discovery without construction, required init inputs, reusable debug session and reset')

            marker = first.id
            expect_error(lambda: sessions.get('run-one', project, 'wrong-marker'), 'another worker')
            sessions.close('run-one')
            expect_error(lambda: sessions.get('run-one', project, marker), 'lost after restart')
            assert not any(key[0] == 'run-one' for key in sessions.sessions)
            lost = sessions.get('killed-run', project)
            lost.process.terminate()
            lost.process.wait(timeout=5)
            expect_error(lambda: lost.call({'binding': {}, 'variables': {}}), 'lost')
            assert sessions.get('killed-run', project, lost.id) is lost
            checks.append('restart markers and terminated worker reject calls without silent recreation')

            twin_dir = directory / 'twin'
            twin_dir.mkdir()
            (twin_dir / 'native_api.py').write_text(SOURCE + '\ndef directory_value():\n    return 42\n', encoding='utf-8')
            twin = {**project, 'path': str(twin_dir), 'factory': ''}
            isolated = sessions.get('run-two', twin)
            assert isolated.id != other.id
            assert call(isolated, 'directory_value', factory='')['result'] == 42
            assert Path(call(isolated, 'environment', factory='')['result']['cwd']) == twin_dir
            environment = call(other, 'environment', factory='')['result']
            assert Path(environment['cwd']) == project_dir, environment
            venv_dir = directory / 'interpreter'
            venv.EnvBuilder(with_pip=False).create(venv_dir)
            executable = venv_dir / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
            alternate = {**project, 'python': str(executable)}
            alternate_session = sessions.get('run-two', alternate)
            assert alternate_session.id != other.id and project_key(alternate) != project_key(project)
            environment = call(alternate_session, 'environment', factory='')['result']
            assert Path(environment['prefix']).resolve() == venv_dir.resolve(), environment
            assert Path(environment['executable']).resolve() == executable.resolve(), environment
            assert select_project({'module': 'native_api', 'factory': 'Device'},
                                  [project_dir], [alternate]) == alternate
            checks.append('same-name modules, project cwd and registered venv interpreter isolation')

            # 使用真实 worker 回调及子进程，builder 只替代 Java 客户端通信边界。
            workflow_values = {'serial': 'callback-device'}
            def callback(function, node, kind='investigationAction'):
                binding = {'module': 'native_api', 'factory': 'Device', 'function': function,
                           'nodeId': node, 'kind': kind}
                job = SimpleNamespace(process_instance_id='callback-run', variables=[
                    SimpleNamespace(name=name, value=value)
                    for name, value in workflow_values.items()])
                builder = CallbackBuilder()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = make_callback(binding, sessions, project)(job, builder)
                assert result is builder
                if not builder.failed:
                    workflow_values.update(builder.values)
                return builder

            assert not callback('collect', 'reading').failed
            marker_name = 'pythonSession_' + project_key(project)
            assert workflow_values[marker_name]
            assert callback('consume', 'consumed').values['consumed']['identical']
            assert callback('decide', 'decision', 'investigation').values['route_decision'] == 'yes'
            assert callback('action', 'restored').values['restored'] is None
            # 人工回退只保留流程当前变量；内存中的旧节点结果不能偷偷补齐被清除的输入。
            saved_reading = workflow_values.pop('reading')
            failure = callback('consume', 'after_rewind')
            assert failure.failed and failure.retry_count == 0, vars(failure)
            assert "missing 1 required positional argument: 'reading'" in failure.error, vars(failure)
            assert 'after_rewind' not in workflow_values
            workflow_values['reading'] = saved_reading
            assert callback('consume', 'after_restore').values['after_restore']['identical']
            checks.append('human rewind removes node input without matching stale native memory results')
            failure = callback('explode', 'broken')
            assert failure.failed and failure.retry_count == 0, vars(failure)
            assert 'native sentinel' in failure.error and 'in explode' in failure.details, vars(failure)
            sessions.close('callback-run')
            failure = callback('consume', 'lost')
            assert failure.failed and failure.retry_count == 0 and 'lost after restart' in failure.error
            assert not any(key[0] == 'callback-run' for key in sessions.sessions)
            checks.append('worker callback variables, native handoff, route, None, failure traceback and restart refusal')

            created_directories = []
            make_directory = tempfile.TemporaryDirectory
            def tracked_directory(*args, **kwargs):
                created = make_directory(*args, **kwargs)
                created_directories.append(Path(created.name))
                return created
            with patch('python_sessions.tempfile.TemporaryDirectory', side_effect=tracked_directory):
                try:
                    sessions.get('bad-interpreter', {**project, 'python': str(directory / 'missing-python')})
                except OSError:
                    pass
                else:
                    raise AssertionError('Invalid interpreter should fail')
            assert created_directories and all(not path.exists() for path in created_directories)
            abandoned = PythonSession(project, 12)
            abandoned_root = abandoned.root
            abandoned_ref = weakref.ref(abandoned)
            del abandoned
            gc.collect()
            assert abandoned_ref() is None and not abandoned_root.exists()

            waiting = sessions.get('closing-run', project)
            waiting_root = waiting.root
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(call, waiting, 'wait_for_close', {'serial': 'closing'})
                deadline = time.monotonic() + 5
                while not (project_dir / 'waiting.txt').exists():
                    assert time.monotonic() < deadline, 'Slow call did not start'
                    time.sleep(0.02)
                sessions.close('closing-run')
                expect_error(lambda: future.result(timeout=5), 'exited')
            assert not waiting_root.exists()
            (project_dir / 'waiting.txt').unlink()
            timeout_session = PythonSession(project, 0.1)
            timeout_root = timeout_session.root
            try:
                call(timeout_session, 'wait_for_close', {'serial': 'timeout'})
            except TimeoutError:
                pass
            else:
                raise AssertionError('Slow call should time out')
            assert timeout_session.closed and not timeout_root.exists()
            checks.append('failed startup, abandoned session, close during active call and timeout release all resources')

            lease_host = 'http://native-verification/' + directory.name
            lease_topics = ['native-reading', 'native-decision']
            child_source = '''
import json
import sys
sys.path.insert(0, sys.argv[1])
from worker_lease import WorkerLease
try:
    lease = WorkerLease(sys.argv[2], json.loads(sys.argv[3]))
except RuntimeError:
    print('blocked')
else:
    print('acquired')
    lease.close()
'''
            def child_lease(host, topics):
                completed = subprocess.run(
                    [sys.executable, '-X', 'utf8', '-c', child_source,
                     str(ROOT / 'backend'), host, json.dumps(topics)],
                    capture_output=True, text=True, encoding='utf-8', timeout=10)
                assert completed.returncode == 0, completed.stderr
                assert not completed.stderr, completed.stderr
                return completed.stdout.strip()

            lease = WorkerLease(lease_host, lease_topics)
            try:
                expect_error(lambda: WorkerLease(lease_host + '/', list(reversed(lease_topics))),
                             'already has a worker')
                assert child_lease(lease_host, list(reversed(lease_topics))) == 'blocked'
                distinct = WorkerLease(lease_host, ['native-other'])
                distinct.close()
                assert child_lease(lease_host, ['native-other-child']) == 'acquired'
                assert child_lease(lease_host + '/another-host', lease_topics) == 'acquired'
            finally:
                lease.close()
            assert child_lease(lease_host, lease_topics) == 'acquired'
            reopened = WorkerLease(lease_host, list(reversed(lease_topics)))
            reopened.close()
            checks.append('worker leases exclude duplicate sorted topics across processes and allow distinct bundles/release')
        finally:
            remaining_roots = [session.root for session in sessions.sessions.values()]
            sessions.close()
            assert all(not path.exists() for path in remaining_roots), remaining_roots
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    for check in checks:
        print('PASS: ' + check)
    print(f'PASS: {len(checks)} native Python verification groups (no Java required)')


if __name__ == '__main__':
    verify()
