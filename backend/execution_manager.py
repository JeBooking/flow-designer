"""仅管理本服务创建的 Flowable 协调器，保留同版本流程的原生会话。"""
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from flowable_worker import select_project
from flowable_bridge import engine_request


BACKEND = Path(__file__).resolve().parent


class WindowsJob:
    """协调器异常退出后仍持有其子进程，服务关闭时整棵树一起回收。"""
    def __init__(self, process):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('minimum', ctypes.c_size_t),
                        ('maximum', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                'read_operations', 'write_operations', 'other_operations',
                'read_bytes', 'write_bytes', 'other_bytes')]

        class Limits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', IoCounters),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                      ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = Limits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class ExecutionManager:
    def __init__(self, registry, timeout=120):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Timeout must be positive and finite')
        self.registry = registry
        self.timeout = timeout
        self.lock = threading.RLock()
        self.workers = {}
        self.closed = False
        self.closing = threading.Event()
        self.recovery_thread = None

    def start_recovery(self):
        if self.recovery_thread:
            return

        def recover():
            last_errors = {}
            definitions = {}
            while not self.closing.is_set():
                try:
                    active_definitions, active_instances = set(), set()
                    for offset in range(0, 200000, 200):
                        page = engine_request('/process-api/runtime/process-instances?start=' + str(offset) + '&size=200', timeout=5)
                        for instance in page['data']:
                            active_instances.add(instance['id'])
                            definition_id = instance['processDefinitionId']
                            if definition_id in active_definitions:
                                continue
                            active_definitions.add(definition_id)
                            if self.closing.is_set():
                                return
                            if definition_id in definitions:
                                identity = definitions[definition_id]
                                with self.lock:
                                    worker = self.workers.get(identity)
                                    if identity is None or worker and worker['process'].poll() is None and worker['ready'].is_file():
                                        continue
                            if time.monotonic() - last_errors.get(instance['id'], (0, ''))[0] < 60:
                                continue
                            try:
                                manifest = engine_request('/diagnosis-api/instances/' + instance['id'] + '/recovery', timeout=5)
                                definitions[definition_id] = self.ensure_worker(json.dumps(manifest))
                            except Exception as error:
                                message = str(error)
                                last_errors[instance['id']] = (time.monotonic(), message)
                                print('Execution recovery deferred: ' + instance['id'] + ': ' + message, file=sys.stderr, flush=True)
                        if len(page['data']) < 200:
                            break
                    definitions = {key: value for key, value in definitions.items() if key in active_definitions}
                    last_errors = {key: value for key, value in last_errors.items() if key in active_instances}
                except Exception as error:
                    if not self.closing.is_set():
                        print('Execution recovery scan failed: ' + str(error), file=sys.stderr, flush=True)
                self.closing.wait(5)

        self.recovery_thread = threading.Thread(target=recover, daemon=True, name='execution-recovery')
        self.recovery_thread.start()

    def ensure_worker(self, bindings):
        if self.closing.is_set():
            raise RuntimeError('Execution manager is closed / 执行管理器已关闭')
        manifest = json.loads(bindings)
        automatic = {topic: binding for topic, binding in manifest['bindings'].items()
                     if binding.get('module')}
        if not automatic:
            return
        with self.lock:
            if self.closing.is_set():
                raise RuntimeError('Execution manager is closed / 执行管理器已关闭')
            with self.registry.lock:
                registered = list(self.registry.projects.values())
                resolved = {topic: select_project(binding, [], registered)
                            for topic, binding in automatic.items()}
            for project in resolved.values():
                if not Path(project['path']).is_dir():
                    raise ValueError('Registered project directory is missing / 已登记工程目录不存在: '
                                     + project['path'])
                if not (Path(project['python']).is_file() or shutil.which(project['python'])):
                    raise ValueError('Registered Python interpreter is missing / 已登记 Python 解释器不存在: '
                                     + project['python'])
                if project.get('moduleFile') and not Path(project['moduleFile']).is_file():
                    raise ValueError('Registered module file is missing / 已登记模块文件不存在: '
                                     + project['moduleFile'])
            canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=True, allow_nan=False)
            content_hash = hashlib.sha256(canonical.encode()).hexdigest()
            host = os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080').rstrip('/')
            identity = hashlib.sha256((host + '\n' + '\n'.join(sorted(automatic))).encode()).hexdigest()
            fields = ('nodeId', 'module', 'factory', 'function', 'kwargs', 'outgoing',
                      'kind', 'humanDecision', 'branches', 'mode')
            # runtime 与会话协议均不消费 detailText；说明和节点名称变化可共用原协调器。
            execution = json.dumps({topic: {key: binding.get(key) for key in fields}
                                    for topic, binding in automatic.items()}, sort_keys=True)
            projects = json.dumps(resolved, sort_keys=True, ensure_ascii=True)
            existing = self.workers.get(identity)
            if existing:
                if existing['process'].poll() is not None or not existing['ready'].is_file():
                    # 协调器可重新订阅；旧实例只能从校验通过的检查点恢复，不能静默重造对象。
                    self._stop(existing)
                    del self.workers[identity]
                else:
                    if existing['projects'] != projects or existing['execution'] != execution:
                        raise RuntimeError('Worker execution or registered project changed / 工作进程执行绑定或工程登记已改变')
                    return identity
            for entry in self.workers.values():
                if set(automatic) & entry['topics']:
                    raise RuntimeError('Topics already belong to a different execution manifest / '
                                       '主题已属于另一执行清单。 Log: ' + str(entry['log']))
            interpreter = next((path for path in (
                BACKEND / '.local' / 'venv' / 'Scripts' / 'python.exe',
                BACKEND / '.local' / 'venv' / 'bin' / 'python') if path.is_file()), Path(sys.executable))
            directory = BACKEND / '.local' / 'executions' / content_hash
            directory.mkdir(parents=True, exist_ok=True)
            launch = uuid.uuid4().hex
            log_file = directory / (launch + '.log')
            ready_file = directory / (launch + '.ready.json')
            bindings_file = directory / 'bindings.json'
            bindings_file.write_text(bindings, encoding='utf-8')
            flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            try:
                with log_file.open('ab', buffering=0) as log:
                    # 仅检查协调器依赖，不导入用户模块，避免部署前执行用户业务初始化。
                    checked = subprocess.run(
                        [str(interpreter), '-X', 'utf8', '-c',
                         'from flowable.external_worker_client import ExternalWorkerClient; from requests.auth import HTTPBasicAuth'],
                        stdout=log, stderr=log, timeout=min(self.timeout, 10), **flags)
                    if checked.returncode:
                        raise RuntimeError('Worker dependencies unavailable / 工作进程依赖不可用。 Log: ' + str(log_file))
                    if self.closing.is_set():
                        raise RuntimeError('Backend is closing / 后端正在关闭')
                    process = subprocess.Popen(
                        [str(interpreter), '-u', '-X', 'utf8', str(BACKEND / 'flowable_worker.py'),
                         str(bindings_file), '--registry', str(self.registry.file.resolve()),
                         '--timeout', str(self.timeout), '--ready-file', str(ready_file)],
                        cwd=str(BACKEND), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        env={**os.environ, 'PYTHONUTF8': '1'},
                        start_new_session=os.name != 'nt', **flags)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise RuntimeError(str(error) + '. Log: ' + str(log_file)) from error
            entry = {'process': process, 'topics': set(automatic), 'projects': projects,
                     'execution': execution, 'log': log_file, 'ready': ready_file, 'job': None}
            self.workers[identity] = entry
            try:
                if os.name == 'nt':
                    entry['job'] = WindowsJob(process)
                deadline = time.monotonic() + min(self.timeout, 60) + 5
                while True:
                    if self.closing.is_set():
                        raise RuntimeError('Backend is closing / 后端正在关闭')
                    if process.poll() is not None:
                        raise RuntimeError('Worker exited during initialization / 工作进程初始化退出')
                    if ready_file.is_file():
                        ready = json.loads(ready_file.read_text(encoding='utf-8'))
                        # Windows venv 的启动器 PID 可能不同；本次 UUID 独占路径证明信号归属。
                        if (not isinstance(ready.get('pid'), int) or ready['pid'] <= 0
                                or ready.get('version') != manifest.get('version')
                                or ready.get('topics') != sorted(automatic)):
                            raise RuntimeError('Worker readiness identity mismatch / 工作进程就绪身份不匹配')
                        return identity
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Worker readiness timed out / 等待工作进程就绪超时')
                    time.sleep(0.05)
            except BaseException as error:
                try:
                    self._stop(entry)
                finally:
                    del self.workers[identity]
                raise RuntimeError(str(error) + '. Log: ' + str(log_file)) from error

    @staticmethod
    def _stop(entry):
        process = entry['process']
        if os.name == 'nt':
            if entry.get('job'):
                entry['job'].close()
            elif process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
                               timeout=15)
        else:
            # 独立进程组仅含本次创建的协调器与业务解释器，不触碰外部引擎。
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.name != 'nt':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        entry['ready'].unlink(missing_ok=True)

    def close(self):
        self.closing.set()
        with self.lock:
            if self.closed:
                return
            self.closed = True
            errors = []
            with ThreadPoolExecutor(max_workers=max(1, len(self.workers))) as pool:
                for result in [pool.submit(self._stop, entry) for entry in self.workers.values()]:
                    try:
                        result.result()
                    except (OSError, subprocess.TimeoutExpired) as error:
                        errors.append(str(error))
            if errors:
                raise RuntimeError('Worker cleanup failed: ' + '; '.join(errors))
        if self.recovery_thread:
            self.recovery_thread.join(timeout=6)
