"""一个执行包使用一个本机协调器，避免相同主题被多个进程分走原生会话。"""
import hashlib
import os
from pathlib import Path
import tempfile


class WorkerLease:
    def __init__(self, host, topics):
        identity = host.rstrip('/') + '\n' + '\n'.join(sorted(topics))
        key = hashlib.sha256(identity.encode()).hexdigest()
        directory = Path(tempfile.gettempdir()) / 'diagnostic-python-workers'
        directory.mkdir(exist_ok=True)
        self.file = (directory / (key + '.lock')).open('a+b')
        self.file.seek(0)
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RuntimeError('This execution bundle already has a worker / 此执行包已有工作进程，请使用已有进程或先将其停止') from error

    def close(self):
        self.file.close()
