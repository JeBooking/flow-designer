"""使用官方 Python 客户端执行绑定函数；业务工程通过普通 Python 导入复用。"""
import argparse
import asyncio
import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import threading
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
    """仅匹配可证明唯一的数据来源；保留默认值，不猜测设备参数。"""
    parameters = inspect.signature(function).parameters
    values = dict(explicit)
    for name, parameter in parameters.items():
        if name in values or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if name in variables:
            values[name] = variables[name]
            continue
        candidates = [value[name] for key, value in variables.items()
                      if not key.startswith(('request_', 'review_', 'route_', 'human_'))
                      and isinstance(value, dict) and name in value]
        if len(candidates) > 1:
            raise ValueError('Ambiguous interface parameter / 接口参数来源不唯一: ' + name)
        if candidates:
            values[name] = candidates[0]
        elif parameter.default is parameter.empty:
            raise ValueError('Missing interface parameter / 缺少接口参数数据: ' + name)
    args = []
    for name, parameter in parameters.items():
        if parameter.kind == parameter.POSITIONAL_ONLY:
            args.append(values.pop(name, parameter.default))
    return args, values


def decision_branch(result, binding):
    value = result.get('next', result.get('result')) if isinstance(result, dict) else result
    if value is True or value in ('yes', '是'):
        return 'yes'
    if value is False or value in ('no', '否'):
        return 'no'
    branch = binding.get('branches', {}).get(value) if isinstance(value, str) else None
    if branch in ('yes', 'no'):
        return branch
    raise ValueError('Investigation must return yes/no / 排查接口必须返回是或否')


def execute(binding, variables):
    module = importlib.import_module(binding['module'])
    function = getattr(module, binding['function'])
    args, kwargs = automatic_arguments(function, resolve(binding.get('kwargs', {}), variables), variables)
    result = function(*args, **kwargs)
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    # 约定只限制执行器需要的路由信息，业务结果仍可采用各工程自己的结构。
    if isinstance(result, HumanDecisionRequest):
        if not isinstance(result.instructions, str):
            raise ValueError('Human decision instructions must be text')
        if binding.get('kind') and binding['kind'] != 'investigation':
            raise ValueError('Only investigations can request judgment / 只有排查节点可请求判断')
        if result.options and set(result.options) not in (set(binding['outgoing']), {'yes', 'no'}):
            raise ValueError('Human decision options must match outgoing flow IDs')
        json.dumps(result.data, allow_nan=False)
        return result
    json.dumps(result, allow_nan=False)
    outgoing = binding['outgoing']
    if (binding.get('kind') == 'investigation' or binding.get('branches')) and not binding.get('humanDecision'):
        decision_branch(result, binding)
    elif not binding.get('kind') and len(outgoing) > 1 and not binding.get('humanDecision'):
        if not isinstance(result, dict) or result.get('next') not in outgoing:
            raise ValueError('Branch function must return {"next": "outgoing flow ID", ...}')
    return result


def make_callback(binding):
    def callback(job, builder):
        variables = {variable.name: variable.value for variable in job.variables}
        result = execute(binding, variables)
        requested = isinstance(result, HumanDecisionRequest)
        manual = requested or bool(binding.get('humanDecision'))
        payload = result.data if requested else result
        success = builder.success().variable_json(binding['nodeId'], payload)
        # 适配层只传递组件请求，不捕获业务异常，也不判断业务代码是否已实现。
        success.variable_boolean('human_' + binding['nodeId'], manual)
        success.variable_json('request_' + binding['nodeId'],
            {'instructions': result.instructions} if requested else {})
        if (binding.get('kind') == 'investigation' or binding.get('branches')) and not manual:
            success.variable_string('route_' + binding['nodeId'], decision_branch(result, binding))
        elif not binding.get('kind') and len(binding['outgoing']) > 1 and not manual:
            success.variable_string('route_' + binding['nodeId'], result['next'])
        print(json.dumps({'node': binding['nodeId'], 'result': payload, 'human': manual}, ensure_ascii=False), flush=True)
        return success
    return callback


def main():
    parser = argparse.ArgumentParser(description='Flowable official Python external worker')
    parser.add_argument('bindings', type=Path)
    parser.add_argument('--project', type=Path, action='append', default=[])
    args = parser.parse_args()
    for project in reversed(args.project):
        sys.path[:0] = [str(project.resolve() / 'src'), str(project.resolve())]
    from flowable.external_worker_client import ExternalWorkerClient
    from requests.auth import HTTPBasicAuth
    manifest = json.loads(args.bindings.read_text(encoding='utf-8-sig'))
    client = ExternalWorkerClient(os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080'),
        auth=HTTPBasicAuth(os.environ.get('FLOWABLE_USER', 'diagnostic'),
                           os.environ.get('FLOWABLE_PASSWORD', 'local-demo')))
    automatic = {topic: binding for topic, binding in manifest['bindings'].items() if binding.get('module')}
    subscriptions = [client.subscribe(topic, make_callback(binding), lock_duration='PT5M',
        wait_period_seconds=1) for topic, binding in automatic.items()]
    print('Subscribed: ' + ', '.join(automatic), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for subscription in subscriptions:
            subscription.unsubscribe()


if __name__ == '__main__':
    main()
