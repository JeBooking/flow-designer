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


def execute(binding, variables):
    module = importlib.import_module(binding['module'])
    function = getattr(module, binding['function'])
    result = function(**resolve(binding['kwargs'], variables))
    if inspect.isawaitable(result):
        result = asyncio.run(result)
    # 约定只限制执行器需要的路由信息，业务结果仍可采用各工程自己的结构。
    json.dumps(result, allow_nan=False)
    outgoing = binding['outgoing']
    if len(outgoing) > 1:
        if not isinstance(result, dict) or result.get('next') not in outgoing:
            raise ValueError('Branch function must return {"next": "outgoing flow ID", ...}')
    return result


def make_callback(binding):
    def callback(job, builder):
        variables = {variable.name: variable.value for variable in job.variables}
        result = execute(binding, variables)
        success = builder.success().variable_json(binding['nodeId'], result)
        if len(binding['outgoing']) > 1:
            success.variable_string('route_' + binding['nodeId'], result['next'])
        print(json.dumps({'node': binding['nodeId'], 'result': result}, ensure_ascii=False), flush=True)
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
    subscriptions = [client.subscribe(topic, make_callback(binding), lock_duration='PT5M',
        wait_period_seconds=1) for topic, binding in manifest['bindings'].items()]
    print('Subscribed: ' + ', '.join(manifest['bindings']), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for subscription in subscriptions:
            subscription.unsubscribe()


if __name__ == '__main__':
    main()
