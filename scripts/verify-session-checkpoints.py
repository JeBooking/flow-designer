"""真实子进程验证持久检查点、原生引用、结果重用及不确定动作的拒绝恢复。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from python_sessions import DurableSessionManager, project_key
from session_checkpoint import CheckpointStore

SOURCE = '''
from pathlib import Path
import threading
__diagnosis_stateless__ = True
barrier = threading.Barrier(2)

class Reading:
    def __init__(self, value): self.value = value
    def __diagnosis_checkpoint__(self): return {'value': self.value}
    @classmethod
    def __diagnosis_restore__(cls, state): return cls(**state)

class Device:
    def __init__(self):
        with Path('constructors.txt').open('a') as stream: stream.write('created\\n')
        self.latest = None
        self.count = 0
    def __diagnosis_checkpoint__(self): return dict(self.__dict__)
    @classmethod
    def __diagnosis_restore__(cls, state):
        instance = object.__new__(cls)
        instance.__dict__.update(state)
        return instance
    def read(self):
        self.latest = Reading(24)
        return self.latest
    def check(self, reading): return self.latest is reading
    def action(self):
        self.count += 1
        with Path('actions.txt').open('a') as stream: stream.write('action\\n')
        return {'count': self.count}
    def parallel(self):
        barrier.wait(timeout=5)
        return {'complete': True}
    def fail(self):
        self.action()
        raise ValueError('after-action sentinel')
'''


def verify():
    with tempfile.TemporaryDirectory(prefix='checkpoint-verification-') as directory:
        directory = Path(directory)
        project_root = directory / 'project'
        project_root.mkdir()
        (project_root / 'checkpoint_fixture.py').write_text(SOURCE, encoding='utf-8')
        project = {'path': str(project_root), 'python': sys.executable}
        checkpoint_root = directory / 'checkpoints'
        manager = DurableSessionManager(10, checkpoint_root, 'verification')
        variables = {}

        def call(session, function, node, job=None):
            result = session.call({'jobId': job or node, 'binding': {'module': 'checkpoint_fixture',
                'factory': 'Device', 'function': function, 'nodeId': node, 'kind': 'investigationAction'},
                'variables': variables})
            if result['ok']:
                variables[node] = result['result']
            return result

        try:
            session = manager.get('run', project)
            identifier = session.id
            assert call(session, 'read', 'reading')['checkpointStatus']['recoverable']
            session.acknowledge('reading')
            first = call(session, 'action', 'action', 'stable-job')
            assert first['result'] == {'count': 1}
            assert call(session, 'action', 'action', 'stable-job')['result'] == first['result']
            assert (project_root / 'actions.txt').read_text().splitlines() == ['action']
            session.acknowledge('stable-job')
            manager.close()
            manager = DurableSessionManager(10, checkpoint_root, 'verification')
            restored = manager.get('run', project, identifier)
            assert restored.id == identifier
            assert call(restored, 'check', 'check')['result'] is True
            restored.acknowledge('check')
            assert (project_root / 'constructors.txt').read_text().splitlines() == ['created']
            process = restored.process
            (project_root / 'checkpoint_fixture.py').write_text(SOURCE + '\n# live update\n', encoding='utf-8')
            manager.suspend('run')
            assert process.poll() is None and manager.sessions
            (project_root / 'checkpoint_fixture.py').write_text(SOURCE, encoding='utf-8')
            manager.suspend('run')
            assert process.poll() is not None and not manager.sessions
            restored = manager.get('run', project, identifier)
            assert call(restored, 'check', 'check-again')['result'] is True
            restored.acknowledge('check-again')
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda name: call(restored, 'parallel', name), ['parallel-a', 'parallel-b']))
            assert all(result['ok'] for result in results)
            assert json.loads(restored.path.read_text())['phase'] == 'ready'
            restored.acknowledge('parallel-a')
            restored.acknowledge('parallel-b')
            failed = call(restored, 'fail', 'failed', 'failed-job')
            assert not failed['ok'] and 'after-action sentinel' in failed['error']
            assert not call(restored, 'fail', 'failed', 'failed-job')['ok']
            assert len((project_root / 'actions.txt').read_text().splitlines()) == 2
            restored.acknowledge('failed-job')
            manager.close()
            path = manager.store.path('run', project_key(project))
            ready = json.loads(path.read_text())
            (project_root / 'checkpoint_fixture.py').write_text(SOURCE + '\n# changed\n', encoding='utf-8')
            manager = DurableSessionManager(10, checkpoint_root, 'verification')
            try:
                manager.get('run', project, identifier)
            except RuntimeError as error:
                assert 'source changed' in str(error)
            else:
                raise AssertionError('Changed source restored silently')
            (project_root / 'checkpoint_fixture.py').write_text(SOURCE, encoding='utf-8')
            incompatible = json.loads(json.dumps(ready))
            incompatible['checkpoint']['environmentSignature'] = 'different-environment'
            CheckpointStore.write(path, incompatible)
            try:
                manager.get('run', project, identifier)
            except RuntimeError as error:
                assert 'environment changed' in str(error)
            else:
                raise AssertionError('Changed environment restored silently')
            CheckpointStore.write(path, {**ready, 'phase': 'inflight'})
            try:
                manager.get('run', project, identifier)
            except RuntimeError as error:
                assert 'incomplete' in str(error)
            else:
                raise AssertionError('Uncertain action restored silently')
            (project_root / 'unsupported.py').write_text('def run(): return True\n', encoding='utf-8')
            unsupported = manager.get('unsupported-run', project)
            result = unsupported.call({'jobId': 'unsupported', 'binding': {'module': 'unsupported',
                'function': 'run', 'nodeId': 'node'}, 'variables': {}})
            assert result['ok'] and not result['checkpointStatus']['recoverable']
            assert 'declare stateless' in result['checkpointStatus']['reason']
            unsupported_id = unsupported.id
            manager.close()
            manager = DurableSessionManager(10, checkpoint_root, 'verification')
            try:
                manager.get('unsupported-run', project, unsupported_id)
            except RuntimeError as error:
                assert 'incomplete' in str(error)
            else:
                raise AssertionError('Unsupported module restored silently')
        finally:
            manager.close()
    with tempfile.TemporaryDirectory(prefix='cooling-checkpoint-') as directory:
        project = {'path': str(ROOT / 'backend/examples/cooling_project'), 'python': sys.executable}
        manager = DurableSessionManager(10, Path(directory), 'cooling-verification')
        variables = {}

        def cooling_call(session, function, node):
            response = session.call({'jobId': node, 'binding': {'module': 'cooling_lab.api',
                'factory': 'CoolingSession', 'function': function, 'nodeId': node,
                'kind': 'investigationAction'}, 'variables': variables})
            assert response['ok'] and response['checkpointStatus']['recoverable'], response
            variables[node] = response['result']
            session.acknowledge(node)
            return response['result']

        try:
            session = manager.get('cooling', project)
            identifier = session.id
            cooling_call(session, 'collect_fan', 'fan_sample')
            cooling_call(session, 'restart_fan', 'repair')
            manager.close()
            manager = DurableSessionManager(10, Path(directory), 'cooling-verification')
            restored = manager.get('cooling', project, identifier)
            assert cooling_call(restored, 'fan_is_faulty', 'check') is True
            report = cooling_call(restored, 'report_fan', 'report')
            assert report['after'] == 42 and report['repairs'] == ['restart_fan']
        finally:
            manager.close()
    print('PASS: persisted native identity, constructor/action exactly once, cached job replay, idle release, concurrent checkpoint barrier, source changes and incomplete/unsupported recovery rejection')
    print('PASS: bundled Cooling native measurements, limits, repaired state and recreated process lock survive restart')


if __name__ == '__main__':
    verify()
