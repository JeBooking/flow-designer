"""单次排查的原生 Python 状态；只在进程通信边界生成展示数据。"""
import asyncio
from datetime import datetime, timezone
import importlib
from importlib import metadata as package_metadata
import hashlib
import inspect
import json
import threading
import typing
import traceback
import uuid
import sys
from pathlib import Path

from diagnostic_components import HumanDecisionRequest
from session_checkpoint import StateCodec, CheckpointUnavailable


def environment_signature():
    return hashlib.sha256(json.dumps([sys.version,
        sorted(((item.metadata.get('Name') or '').lower(), item.version)
               for item in package_metadata.distributions())]).encode()).hexdigest()


def business_variables(variables):
    return {key: value for key, value in variables.items()
            if not key.startswith(('executionTrace_', 'selectedRoutes_', 'pythonCheckpoint_'))}


def trace_time():
    return datetime.now(timezone.utc).isoformat()


def freeze_display(value):
    # JSON 往返切断引用，防止业务函数后续修改原生对象时改写历史展示。
    return json.loads(json.dumps(display_value(value), ensure_ascii=False, allow_nan=False))


def call_inputs(function, args, kwargs):
    try:
        bound = inspect.signature(function).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return freeze_display(dict(bound.arguments))
    except TypeError:
        # 无效实参也保留原样，调用错误由原函数产生，保持已有错误信息。
        return freeze_display({'args': args, 'kwargs': kwargs})


def new_execution_trace(binding):
    trace = {'version': 1, 'id': uuid.uuid4().hex, 'nodeId': binding.get('nodeId', ''),
             'startedAt': trace_time(), 'call': {key: binding.get(key, '')
                                              for key in ('module', 'factory', 'function')}}
    if isinstance(binding.get('instructions'), dict):
        trace['instructions'] = freeze_display(binding['instructions'])
    return trace


def resolve(value, variables):
    variables = business_variables(variables)
    if isinstance(value, str) and value.startswith('$'):
        if value.startswith('$$'):
            return value[1:]
        if value == '$':
            return variables
        current = variables
        for part in value[1:].split('.'):
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current
    if isinstance(value, list):
        return [resolve(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, variables) for key, item in value.items()}
    return value


def automatic_arguments(function, explicit, variables):
    """遵守 Python 签名和默认值；只有数据来源唯一时才自动传入。"""
    variables = business_variables(variables)
    parameters = inspect.signature(function).parameters
    values = dict(explicit)
    for name, parameter in parameters.items():
        if name in values or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name in variables:
            values[name] = variables[name]
            continue
        candidates = [value[name] for key, value in variables.items()
                      if not key.startswith(('request_', 'review_', 'route_', 'human_', 'pythonSession_'))
                      and isinstance(value, dict) and name in value]
        if len(candidates) > 1:
            raise ValueError('Ambiguous interface parameter / 接口参数来源不唯一: ' + name)
        if candidates:
            values[name] = candidates[0]
        elif parameter.default is parameter.empty:
            # 让 Python 本身生成缺参错误，保留真实的函数名称和调用规则。
            continue
    args = []
    positional = [p for p in parameters.values() if p.kind == p.POSITIONAL_ONLY]
    last = max((i for i, p in enumerate(positional) if p.name in values), default=-1)
    for parameter in positional[:last + 1]:
        if parameter.name in values:
            args.append(values.pop(parameter.name))
        elif parameter.default is not parameter.empty:
            args.append(parameter.default)
        else:
            raise TypeError('Missing positional-only argument: ' + parameter.name)
    return args, values


def decision_branch(result, binding):
    value = result.get('next', result.get('result')) if isinstance(result, dict) else result
    if value is True or isinstance(value, str) and value.lower() in ('yes', '是'):
        return 'yes'
    if value is False or isinstance(value, str) and value.lower() in ('no', '否'):
        return 'no'
    branch = binding.get('branches', {}).get(value) if isinstance(value, str) else None
    if branch in ('yes', 'no'):
        return branch
    raise ValueError('Investigation must return yes/no / 排查接口必须返回是或否')


def public_members(module):
    names = getattr(module, '__all__', None)
    if names is None:
        names = [name for name, value in vars(module).items()
                 if not name.startswith('_') and (inspect.isroutine(value) or inspect.isclass(value))
                 and getattr(value, '__module__', None) == module.__name__]
    return {name: getattr(module, name) for name in names
            if isinstance(name, str) and not name.startswith('_') and callable(getattr(module, name, None))}


def member(owner, path):
    for name in path.split('.'):
        if not name.isidentifier() or name.startswith('_'):
            raise ValueError('Use a public Python callable / 请选择公开的 Python 接口: ' + path)
        owner = getattr(owner, name)
    return owner


def parameter_info(function):
    try:
        parameters = inspect.signature(function).parameters.values()
    except (ValueError, TypeError):
        return []
    return [{'name': p.name, 'kind': p.kind.name,
             'required': p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD),
             **({'default': repr(p.default)} if p.default is not p.empty else {}),
             **({'annotation': inspect.formatannotation(p.annotation)} if p.annotation is not p.empty else {})}
            for p in parameters]


def describe(function, name, unbound=False):
    signature = inspect.signature(function)
    if unbound:
        signature = signature.replace(parameters=list(signature.parameters.values())[1:])
    parameters = parameter_info(function)
    if unbound:
        parameters = parameters[1:]
    return {'name': name, 'signature': str(signature), 'parameters': parameters,
            'description': inspect.getdoc(function) or ''}


def describe_instance(owner):
    result = []
    for name in dir(owner):
        if name.startswith('_'):
            continue
        # 不执行 property 等描述符，发现接口不能触发业务读取。
        descriptor = inspect.getattr_static(owner, name)
        if isinstance(descriptor, property):
            continue
        function = getattr(owner, name)
        if inspect.isroutine(function):
            result.append(describe(function, name, inspect.isclass(owner) and inspect.isfunction(descriptor)))
    return result


def display_value(value, seen=None, depth=0):
    """展示投影永远不写回原始结果；对象引用和循环结构留在会话内。"""
    try:
        json.dumps(value, allow_nan=False)
        return value
    except (TypeError, ValueError, OverflowError):
        pass
    seen = set() if seen is None else seen
    if depth < 8 and id(value) not in seen:
        seen = seen | {id(value)}
        if isinstance(value, dict) and all(isinstance(key, str) for key in value):
            return {key: display_value(item, seen, depth + 1) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [display_value(item, seen, depth + 1) for item in value]
    try:
        representation = repr(value)
    except Exception:
        representation = '<repr failed>'
    return {'pythonType': type(value).__module__ + '.' + type(value).__qualname__,
            'representation': representation, 'native': True}


class NativeRuntime:
    def __init__(self, checkpoint_root=None):
        self.instances = {}
        self.factory_inputs = {}
        self.results = {}
        self.modules = set()
        self.checkpoint_root = checkpoint_root
        self.environment_signature = environment_signature() if checkpoint_root else None
        self.lock = threading.RLock()
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.loop_thread.start()

    def wait(self, value):
        if not inspect.isawaitable(value):
            return value
        async def await_value():
            return await value
        return asyncio.run_coroutine_threadsafe(await_value(), self.loop).result()

    def target(self, module_name, factory, variables, trace=None):
        module = importlib.import_module(module_name)
        with self.lock:
            self.modules.add(module_name)
        if not factory:
            return module
        key = (module_name, factory)
        with self.lock:
            if key not in self.instances:
                create = member(module, factory)
                args, kwargs = automatic_arguments(create, {}, variables)
                initial_inputs = call_inputs(create, args, kwargs)
                if trace is not None:
                    trace['factoryInputs'] = initial_inputs
                self.instances[key] = self.wait(create(*args, **kwargs))
                self.factory_inputs[key] = initial_inputs
            if trace is not None:
                # 复用实例只能引用创建时输入；本轮变量不能冒充最初的构造参数。
                trace['factoryInputs'] = freeze_display(self.factory_inputs[key])
            return self.instances[key]

    def discover(self, module_name, factory='', inputs=None):
        module = importlib.import_module(module_name)
        initial = []
        if factory:
            create = member(module, factory)
            initial = parameter_info(create)
            if inspect.isclass(create):
                owner = create
            else:
                try:
                    owner = typing.get_type_hints(create).get('return')
                except (NameError, TypeError):
                    owner = None
                if not inspect.isclass(owner):
                    owner = self.target(module_name, factory, inputs or {})
            interfaces = describe_instance(owner)
        else:
            interfaces = [describe(function, name) for name, function in public_members(module).items()
                          if inspect.isroutine(function)]
        return {'interfaces': interfaces, 'initParameters': initial,
                'moduleFile': str(module.__file__)}

    def execute(self, binding, variables, trace=None):
        if trace is None:
            trace = new_execution_trace(binding)
        elif not trace.get('id'):
            trace.update(new_execution_trace(binding))
        try:
            return self._execute(binding, variables, trace)
        except BaseException as error:
            trace.update(status='failed', error=f'{type(error).__name__}: {error}',
                         traceback=traceback.format_exc())
            raise
        finally:
            trace['endedAt'] = trace_time()

    def _execute(self, binding, variables, trace):
        with self.lock:
            values = business_variables({**variables, **{key: value for key, value in self.results.items()
                                                        if key in variables}})
        owner = self.target(binding['module'], binding.get('factory', ''), values, trace)
        function = member(owner, binding['function'])
        explicit = resolve(binding.get('kwargs', {}), values)
        trace['inputs'] = freeze_display(explicit)
        args, kwargs = automatic_arguments(function, explicit, values)
        trace['inputs'] = call_inputs(function, args, kwargs)
        result = self.wait(function(*args, **kwargs))
        trace['evidence'] = freeze_display(result.data if isinstance(result, HumanDecisionRequest) else result)
        if not isinstance(result, HumanDecisionRequest):
            trace['result'] = freeze_display(trace['evidence'])
        if isinstance(result, HumanDecisionRequest):
            if not isinstance(result.instructions, str):
                raise ValueError('Human decision instructions must be text')
            trace['judgmentInstructions'] = result.instructions
            if binding.get('kind') and binding['kind'] != 'investigation':
                raise ValueError('Only investigations can request judgment / 只有排查节点可请求判断')
            if result.options and set(result.options) not in (set(binding.get('outgoing', [])), {'yes', 'no'}):
                raise ValueError('Human decision options must match outgoing flow IDs')
        elif (binding.get('kind') == 'investigation' or binding.get('branches')) and not binding.get('humanDecision'):
            trace['route'] = decision_branch(result, binding)
        elif not binding.get('kind') and len(binding.get('outgoing', [])) > 1 and not binding.get('humanDecision'):
            if not isinstance(result, dict) or result.get('next') not in binding['outgoing']:
                raise ValueError('Branch function must return {"next": "outgoing flow ID", ...}')
            trace['route'] = result['next']
        trace['status'] = 'waiting' if isinstance(result, HumanDecisionRequest) or binding.get('humanDecision') else 'completed'
        if binding.get('nodeId'):
            with self.lock:
                self.results[binding['nodeId']] = result.data if isinstance(result, HumanDecisionRequest) else result
        return result

    def checkpoint(self):
        modules = []
        for name in sorted(self.modules):
            module = importlib.import_module(name)
            export = getattr(module, '__diagnosis_checkpoint__', None)
            restore = getattr(module, '__diagnosis_restore__', None)
            if callable(export) and callable(restore):
                state = json.loads(json.dumps(self.wait(export()), allow_nan=False))
                modules.append({'module': name, 'state': state})
            elif getattr(module, '__diagnosis_stateless__', False) is True:
                modules.append({'module': name, 'stateless': True})
            else:
                raise CheckpointUnavailable('Module must declare stateless globals or checkpoint hooks / 模块需要声明全局无状态或提供检查点接口: ' + name)
        state = {'instances': [{'module': name, 'factory': factory, 'value': instance,
            'inputs': self.factory_inputs[(name, factory)]} for (name, factory), instance in self.instances.items()],
            'results': self.results}
        return {'version': 1, 'environmentSignature': self.environment_signature,
            'modules': modules, 'state': StateCodec(self.checkpoint_root).encode(state)}

    def restore_checkpoint(self, snapshot):
        if snapshot.get('version') != 1:
            raise CheckpointUnavailable('Unsupported runtime checkpoint / 不支持此检查点版本')
        if snapshot.get('environmentSignature') != self.environment_signature:
            raise CheckpointUnavailable('Python environment changed since checkpoint / 检查点之后 Python 或依赖环境已改变')
        for entry in snapshot['modules']:
            module = importlib.import_module(entry['module'])
            if Path(self.checkpoint_root).resolve() not in Path(module.__file__).resolve().parents:
                raise CheckpointUnavailable('Checkpoint module is outside the registered project / 检查点模块不属于登记工程')
            if not entry.get('stateless'):
                self.wait(module.__diagnosis_restore__(entry['state']))
            elif getattr(module, '__diagnosis_stateless__', False) is not True:
                raise CheckpointUnavailable('Module stateless declaration changed / 模块无状态声明已改变')
            self.modules.add(entry['module'])
        state = StateCodec(self.checkpoint_root).decode(snapshot['state'])
        self.instances = {(entry['module'], entry['factory']): entry['value'] for entry in state['instances']}
        self.factory_inputs = {(entry['module'], entry['factory']): entry['inputs'] for entry in state['instances']}
        self.results = state['results']

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(timeout=2)
        self.loop.close()
