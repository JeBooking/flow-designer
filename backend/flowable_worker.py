"""Flowable 调度任务，业务代码在每次排查独立的原生 Python 会话内运行。"""
import argparse
import atexit
import json
import math
import os
from pathlib import Path
import sys
import threading
import traceback

from python_runtime import NativeRuntime, automatic_arguments, decision_branch, resolve
from python_sessions import SessionManager, project_key
from worker_lease import WorkerLease


def execute(binding, variables):
    """直接调用入口供组件工具使用；真实流程使用隔离会话。"""
    runtime = NativeRuntime()
    try:
        return runtime.execute(binding, variables)
    finally:
        runtime.close()


def select_project(binding, projects, registered):
    candidates = [project for project in registered
                  if project['module'] == binding['module']
                  and project.get('factory', '') == binding.get('factory', '')]
    if projects:
        candidates = [project for project in candidates if Path(project['path']).resolve() in projects]
    identities = {(str(Path(project['path']).resolve()), project['python']) for project in candidates}
    if len(identities) > 1:
        raise ValueError('Multiple matching projects; select one with --project / 同名模块来自多个工程，请用 --project 指定目录')
    if candidates:
        return candidates[0]
    module_path = Path(*binding['module'].split('.'))
    for project in projects:
        if any((root / module_path).with_suffix('.py').is_file()
               or (root / module_path / '__init__.py').is_file()
               for root in (project / 'src', project)):
            return {'path': str(project), 'python': sys.executable, 'module': binding['module']}
    if projects:
        raise ValueError('Module is not in selected project / 指定工程中找不到模块: ' + binding['module'])
    raise ValueError('Register the project or use --project / 请先登记工程或使用 --project: ' + binding['module'])


def make_callback(binding, sessions=None, project=None, checkpoint=None):
    def callback(job, builder):
        variables = {variable.name: variable.value for variable in job.variables}
        try:
            if sessions is None or project is None:
                raise RuntimeError('Python session manager is required')
            marker = 'pythonSession_' + project_key(project)
            session = sessions.get(job.process_instance_id, project, variables.get(marker))
            if checkpoint and not variables.get(marker):
                # 调用业务前保存归属，首次节点抛异常后重启也不能静默重造对象。
                checkpoint(job.process_instance_id, marker, session.id)
            response = session.call({'binding': binding, 'variables': variables})
            for stream in ('stdout', 'stderr'):
                if response.get(stream):
                    print(response[stream], end='', file=sys.stderr if stream == 'stderr' else sys.stdout, flush=True)
            if not response['ok']:
                return (builder.failure().error_message(binding['nodeId'] + ': ' + response['error'])
                        .error_details(response['traceback']).retries(0))
            success = builder.success().variable_json(binding['nodeId'], response['result'])
            success.variable_string(marker, session.id)
            success.variable_boolean('human_' + binding['nodeId'], response['human'])
            success.variable_json('request_' + binding['nodeId'], response['request'])
            if 'route' in response:
                success.variable_string('route_' + binding['nodeId'], response['route'])
            print(json.dumps({'node': binding['nodeId'], 'result': response['result'],
                              'human': response['human']}, ensure_ascii=False), flush=True)
            return success
        except Exception as error:
            details = traceback.format_exc()
            print(details, file=sys.stderr, flush=True)
            return (builder.failure().error_message(binding['nodeId'] + ': ' + str(error))
                    .error_details(details).retries(0))
    return callback


def main():
    parser = argparse.ArgumentParser(description='Flowable worker with per-run native Python sessions')
    parser.add_argument('bindings', type=Path)
    parser.add_argument('--project', type=Path, action='append', default=[])
    parser.add_argument('--registry', type=Path, default=Path(__file__).parent / '.local' / 'projects.json')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    projects = [path.resolve() for path in args.project]
    registered = list(json.loads(args.registry.read_text(encoding='utf-8')).values()) if args.registry.exists() else []
    from flowable.external_worker_client import ExternalWorkerClient
    from requests.auth import HTTPBasicAuth
    import requests
    manifest = json.loads(args.bindings.read_text(encoding='utf-8-sig'))
    host = os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080')
    auth = HTTPBasicAuth(os.environ.get('FLOWABLE_USER', 'diagnostic'),
                         os.environ.get('FLOWABLE_PASSWORD', 'local-demo'))
    client = ExternalWorkerClient(host, auth=auth)
    sessions = SessionManager(args.timeout)
    atexit.register(sessions.close)
    automatic = {topic: binding for topic, binding in manifest['bindings'].items() if binding.get('module')}
    lease = WorkerLease(host, automatic)
    atexit.register(lease.close)
    resolved = {topic: select_project(binding, projects, registered) for topic, binding in automatic.items()}
    def checkpoint(run_id, marker, session_id):
        from flowable_bridge import engine_request
        engine_request('/process-api/runtime/process-instances/' + run_id + '/variables',
                       json.dumps([{'name': marker, 'type': 'string', 'value': session_id}]).encode())
    subscriptions = [client.subscribe(topic, make_callback(binding, sessions, resolved[topic], checkpoint),
                     lock_duration=f'PT{max(300, math.ceil(args.timeout) + 60)}S', wait_period_seconds=1)
                     for topic, binding in automatic.items()]
    print('Subscribed: ' + ', '.join(automatic), flush=True)
    try:
        while True:
            threading.Event().wait(10)
            with sessions.lock:
                runs = {key[0] for key in sessions.sessions}
            for run_id in runs:
                try:
                    response = requests.get(host.rstrip('/') + '/process-api/runtime/process-instances/' + run_id,
                                            auth=auth, timeout=5)
                    if response.status_code == 404:
                        sessions.close(run_id)
                except requests.RequestException:
                    # 引擎暂时断开不代表流程结束，保留人工等待中的实例。
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        for subscription in subscriptions:
            subscription.unsubscribe(timeout=10)
        sessions.close()
        lease.close()


if __name__ == '__main__':
    main()
