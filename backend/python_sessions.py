"""按流程实例隔离业务解释器，通信仅传调用信息和展示结果。"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import weakref


def project_key(project):
    identity = str(Path(project['path']).resolve()) + '\n' + project.get('python', sys.executable)
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    if os.name == 'nt':
        # venv 的 python.exe 是启动器，只终止它会留下持有日志和工程目录的业务子进程。
        stopped = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                 capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if stopped.returncode and process.poll() is None:
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def release_resources(process, streams, directory):
    # Windows 删除目录前必须先停子进程并关闭父进程的日志句柄。
    stop_process(process)
    if process is not None and process.stdin is not None:
        process.stdin.close()
    for stream in streams:
        stream.close()
    directory.cleanup()


class PythonSession:
    def __init__(self, project, timeout):
        self.id = uuid.uuid4().hex
        self.timeout = timeout
        self.directory = tempfile.TemporaryDirectory(prefix='diagnostic-session-')
        self.root = Path(self.directory.name)
        self.lock = threading.Lock()
        self.closed = False
        self.active_calls = 0
        streams = []
        process = None
        try:
            configuration = self.root / 'project.json'
            configuration.write_text(json.dumps(project), encoding='utf-8')
            self.stdout = (self.root / 'stdout.log').open('wb')
            streams.append(self.stdout)
            self.stderr = (self.root / 'stderr.log').open('wb')
            streams.append(self.stderr)
            process = self.process = subprocess.Popen(
                [project.get('python') or sys.executable, '-u', '-X', 'utf8',
                 str(Path(__file__).resolve().with_name('python_session_worker.py')), str(configuration)],
                stdin=subprocess.PIPE, stdout=self.stdout, stderr=self.stderr,
                text=True, encoding='utf-8', cwd=project['path'],
                env={**os.environ, 'PYTHONUTF8': '1'})
            # 不能绑定 self，否则 finalizer 会保活整个会话，失去兜底清理作用。
            self.finalize = weakref.finalize(self, release_resources, process, streams, self.directory)
        except BaseException:
            release_resources(process, streams, self.directory)
            raise

    def call(self, request):
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError('Python session lost / Python 会话已丢失，请重新开始排查或重置调试会话')
            self.active_calls += 1
        try:
            return self._call(request)
        finally:
            with self.lock:
                self.active_calls -= 1
                if self.closed and self.active_calls == 0:
                    self.finalize()

    def _call(self, request):
        request_id = uuid.uuid4().hex
        source = self.root / (request_id + '.json')
        destination = source.with_suffix('.result')
        with self.lock:
            if self.closed or self.process.poll() is not None:
                raise RuntimeError('Python session lost / Python 会话已丢失，请重新开始排查或重置调试会话')
            offsets = {name: (self.root / (name + '.log')).stat().st_size for name in ('stdout', 'stderr')}
            source.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
            self.process.stdin.write(str(source) + '\n')
            self.process.stdin.flush()
        deadline = time.monotonic() + self.timeout
        while not destination.exists():
            if self.closed or self.process.poll() is not None:
                raise RuntimeError('Python session exited / Python 会话意外退出')
            if time.monotonic() >= deadline:
                # 超时后继续执行的设备动作不可被当成新会话静默重试。
                self.close()
                raise TimeoutError('Python call timed out; session closed / Python 调用超时，会话已关闭')
            time.sleep(0.02)
        response = json.loads(destination.read_text(encoding='utf-8'))
        for name, offset in offsets.items():
            with (self.root / (name + '.log')).open('rb') as log:
                log.seek(offset)
                response[name] = log.read().decode('utf-8', errors='replace')
        response['sessionId'] = self.id
        source.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        return response

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            stop_process(self.process)
            # 关闭会话时已有调用可能仍在读取响应，最后一个调用退出后再删除目录。
            if self.active_calls == 0:
                self.finalize()


class SessionManager:
    def __init__(self, timeout=120):
        self.timeout = timeout
        self.sessions = {}
        self.lock = threading.RLock()

    def get(self, run_id, project, expected=None):
        key = (run_id, project_key(project))
        with self.lock:
            session = self.sessions.get(key)
            if session is None:
                if expected:
                    raise RuntimeError('Python session lost after restart / Python 会话已丢失，无法自动恢复内存对象；请重新开始排查')
                session = self.sessions[key] = PythonSession(project, self.timeout)
            if expected and expected != session.id:
                raise RuntimeError('Python session belongs to another worker / Python 会话由其他工作进程持有')
            return session

    def close(self, run_id=None):
        with self.lock:
            keys = [key for key in self.sessions if run_id is None or key[0] == run_id]
            for key in keys:
                self.sessions.pop(key).close()
