"""业务显式声明的检查点协议；不使用 pickle，不执行构造函数或重放业务调用。"""
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import uuid


class CheckpointUnavailable(ValueError):
    pass


class StateCodec:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.references = {}
        self.active_custom = set()

    def encode(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            json.dumps(value, allow_nan=False)
            return value
        identity = id(value)
        if identity in self.active_custom:
            raise CheckpointUnavailable('Custom checkpoint state contains a cycle / 自定义检查点存在循环引用')
        if identity in self.references:
            return {'ref': self.references[identity]}
        key = str(len(self.references))
        self.references[identity] = key
        if isinstance(value, dict) and all(isinstance(name, str) for name in value):
            return {'id': key, 'type': 'dict', 'items': {name: self.encode(item) for name, item in value.items()}}
        if isinstance(value, list):
            return {'id': key, 'type': 'list', 'items': [self.encode(item) for item in value]}
        if isinstance(value, tuple):
            self.active_custom.add(identity)
            try:
                return {'id': key, 'type': 'tuple', 'items': [self.encode(item) for item in value]}
            finally:
                self.active_custom.remove(identity)
        owner = type(value)
        self.check_type(owner)
        export = getattr(value, '__diagnosis_checkpoint__', None)
        restore = getattr(owner, '__diagnosis_restore__', None)
        if not callable(export) or not callable(restore):
            raise CheckpointUnavailable('Native object requires checkpoint/restore hooks / 原生对象需要检查点与恢复接口: ' + owner.__qualname__)
        if inspect.iscoroutinefunction(export) or inspect.iscoroutinefunction(restore):
            raise CheckpointUnavailable('Object checkpoint hooks must be synchronous / 对象检查点接口必须同步执行')
        self.active_custom.add(identity)
        try:
            exported = export()
            inspect.signature(restore).bind(exported)
            state = self.encode(exported)
        finally:
            self.active_custom.remove(identity)
        return {'id': key, 'type': 'object', 'module': owner.__module__, 'class': owner.__qualname__, 'state': state}

    def check_type(self, owner):
        path = Path(inspect.getfile(owner)).resolve()
        if self.root not in path.parents or '<locals>' in owner.__qualname__:
            raise CheckpointUnavailable('Checkpoint type must belong to the registered project / 检查点类型必须来自登记工程')

    def decode(self, value):
        if not isinstance(value, dict):
            return value
        if 'ref' in value:
            return self.references[value['ref']]
        kind, key = value['type'], value['id']
        if kind == 'dict':
            result = self.references[key] = {}
            result.update((name, self.decode(item)) for name, item in value['items'].items())
        elif kind in ('list', 'tuple'):
            result = self.references[key] = []
            result.extend(self.decode(item) for item in value['items'])
            if kind == 'tuple':
                result = self.references[key] = tuple(result)
        elif kind == 'object':
            owner = importlib.import_module(value['module'])
            for name in value['class'].split('.'):
                if not name.isidentifier() or name.startswith('_'):
                    raise CheckpointUnavailable('Invalid checkpoint type / 检查点类型无效')
                owner = getattr(owner, name)
            self.check_type(owner)
            result = owner.__diagnosis_restore__(self.decode(value['state']))
            if not isinstance(result, owner):
                raise CheckpointUnavailable('Restore hook returned a different type / 恢复接口返回了不同类型')
            self.references[key] = result
        else:
            raise CheckpointUnavailable('Unknown checkpoint value type / 未知检查点类型')
        return result


def source_signature(project):
    root = Path(project['path']).resolve()
    digest = hashlib.sha256()
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if not name.startswith('.') and name not in ('__pycache__', 'node_modules', 'venv'))
        for name in sorted(files):
            if name.endswith('.py'):
                path = Path(directory) / name
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(b'\0')
                digest.update(path.read_bytes())
    return digest.hexdigest()


class CheckpointStore:
    def __init__(self, directory, identity):
        self.directory = Path(directory) / hashlib.sha256(identity.encode()).hexdigest()

    def path(self, run_id, project_id):
        return self.directory / hashlib.sha256((run_id + '\n' + project_id).encode()).hexdigest()

    def load(self, path, project, expected=None):
        if not path.exists():
            return None
        if path.stat().st_size > 64 * 1024 * 1024:
            raise RuntimeError('Python checkpoint exceeds 64 MiB / 检查点超过 64 MiB')
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('version') != 1 or value.get('phase') != 'ready':
            raise RuntimeError('Python checkpoint is incomplete; inspect the last action before restarting / 检查点未完成，请确认最后一次动作状态后重新排查')
        if expected and value['sessionId'] != expected:
            raise RuntimeError('Python checkpoint session mismatch / 检查点会话不匹配')
        if value['sourceSignature'] != source_signature(project):
            raise RuntimeError('Python source changed since checkpoint / 检查点之后业务代码已改变，无法自动恢复')
        return value

    @staticmethod
    def write(path, value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(payload) > 64 * 1024 * 1024:
            raise CheckpointUnavailable('Python checkpoint exceeds 64 MiB / 检查点超过 64 MiB')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with temporary.open('wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
