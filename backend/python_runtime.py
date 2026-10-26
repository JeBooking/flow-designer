"""单次排查的原生 Python 状态；只在进程通信边界生成展示数据。"""
import asyncio
import importlib
import inspect
import json
import threading
import typing

from diagnostic_components import HumanDecisionRequest


def resolve(value, variables):
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
    def __init__(self):
        self.instances = {}
        self.results = {}
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

    def target(self, module_name, factory, variables):
        module = importlib.import_module(module_name)
        if not factory:
            return module
        key = (module_name, factory)
        with self.lock:
            if key not in self.instances:
                create = member(module, factory)
                args, kwargs = automatic_arguments(create, {}, variables)
                self.instances[key] = self.wait(create(*args, **kwargs))
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

    def execute(self, binding, variables):
        with self.lock:
            values = {**variables, **{key: value for key, value in self.results.items() if key in variables}}
        owner = self.target(binding['module'], binding.get('factory', ''), values)
        function = member(owner, binding['function'])
        args, kwargs = automatic_arguments(function, resolve(binding.get('kwargs', {}), values), values)
        result = self.wait(function(*args, **kwargs))
        if isinstance(result, HumanDecisionRequest):
            if not isinstance(result.instructions, str):
                raise ValueError('Human decision instructions must be text')
            if binding.get('kind') and binding['kind'] != 'investigation':
                raise ValueError('Only investigations can request judgment / 只有排查节点可请求判断')
            if result.options and set(result.options) not in (set(binding.get('outgoing', [])), {'yes', 'no'}):
                raise ValueError('Human decision options must match outgoing flow IDs')
        elif (binding.get('kind') == 'investigation' or binding.get('branches')) and not binding.get('humanDecision'):
            decision_branch(result, binding)
        elif not binding.get('kind') and len(binding.get('outgoing', [])) > 1 and not binding.get('humanDecision'):
            if not isinstance(result, dict) or result.get('next') not in binding['outgoing']:
                raise ValueError('Branch function must return {"next": "outgoing flow ID", ...}')
        if binding.get('nodeId'):
            with self.lock:
                self.results[binding['nodeId']] = result.data if isinstance(result, HumanDecisionRequest) else result
        return result

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(timeout=2)
        self.loop.close()
