"""Flowable 调度任务，业务代码在每次排查独立的原生 Python 会话内运行。"""
import argparse
import atexit
import json
import math
import os
from pathlib import Path
import signal
import sys
import threading
import time
import traceback
import uuid

from python_runtime import (NativeRuntime, automatic_arguments, decision_branch,
                            new_execution_trace, resolve, trace_time)
from python_sessions import DurableSessionManager, project_key
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


def checkpointed_result(result, session, job_id):
    if not hasattr(session, 'acknowledge'):
        return result

    class CheckpointedResult:
        def execute(self, client):
            result.execute(client)
            try:
                session.acknowledge(str(job_id))
            except Exception:
                # 引擎已提交后不能把清理失败当成业务失败；保留缓存只会多占空间。
                traceback.print_exc()
    return CheckpointedResult()


def make_callback(binding, sessions=None, project=None, checkpoint=None):
    def callback(job, builder):
        trace = new_execution_trace(binding)
        job_id = getattr(job, 'id', None) or getattr(job, 'job_id', None)
        if job_id is not None:
            trace['jobId'] = str(job_id)
        trace_name = 'executionTrace_' + trace['id']
        variables = {variable.name: variable.value for variable in job.variables}

        def save_failed_trace():
            # 保存失败不能掩盖业务异常，也不能重新执行已经发生的设备动作。
            try:
                if checkpoint is None:
                    raise RuntimeError('Execution trace checkpoint is unavailable')
                checkpoint(job.process_instance_id, trace_name, trace)
            except Exception:
                print('Failed to persist execution trace ' + trace_name,
                      file=sys.stderr, flush=True)
                traceback.print_exc()

        session = None
        try:
            if sessions is None or project is None:
                raise RuntimeError('Python session manager is required')
            marker = 'pythonSession_' + project_key(project)
            session = sessions.get(job.process_instance_id, project, variables.get(marker))
            if checkpoint and not variables.get(marker):
                # 调用业务前保存归属，首次节点抛异常后重启也不能静默重造对象。
                checkpoint(job.process_instance_id, marker, session.id)
            response = session.call({'binding': binding, 'variables': variables, 'trace': trace, 'jobId': job_id})
            trace.update(response.get('trace', {}))
            for stream in ('stdout', 'stderr'):
                if response.get(stream):
                    print(response[stream], end='', file=sys.stderr if stream == 'stderr' else sys.stdout, flush=True)
            if not response['ok']:
                trace.update(status='failed', error=response['error'], traceback=response['traceback'])
                trace.setdefault('endedAt', trace_time())
                save_failed_trace()
                return checkpointed_result(builder.failure().error_message(binding['nodeId'] + ': ' + response['error'])
                        .error_details(response['traceback']).retries(0), session, job_id)
            trace.setdefault('endedAt', trace_time())
            trace.setdefault('status', 'waiting' if response['human'] else 'completed')
            success = builder.success().variable_json(binding['nodeId'], response['result'])
            success.variable_json('selectedRoutes_' + binding['nodeId'], None)
            success.variable_json(trace_name, trace)
            success.variable_string(marker, session.id)
            success.variable_boolean('human_' + binding['nodeId'], response['human'])
            if 'checkpointStatus' in response:
                success.variable_json('pythonCheckpoint_' + project_key(project), response['checkpointStatus'])
            success.variable_json('request_' + binding['nodeId'], response['request'])
            if 'route' in response:
                success.variable_string('route_' + binding['nodeId'], response['route'])
            print(json.dumps({'node': binding['nodeId'], 'result': response['result'],
                              'human': response['human']}, ensure_ascii=False), flush=True)
            return checkpointed_result(success, session, job_id)
        except Exception as error:
            details = traceback.format_exc()
            print(details, file=sys.stderr, flush=True)
            # 引擎结果构建失败不代表模块调用失败，保留会话已经确定的调用状态。
            if 'status' not in trace:
                trace.update(status='failed', error=f'{type(error).__name__}: {error}', traceback=details)
            trace.setdefault('endedAt', trace_time())
            save_failed_trace()
            return checkpointed_result(builder.failure().error_message(binding['nodeId'] + ': ' + str(error))
                    .error_details(details).retries(0), session, job_id)
    return callback


def main():
    parser = argparse.ArgumentParser(description='Flowable worker with per-run native Python sessions')
    parser.add_argument('bindings', type=Path)
    parser.add_argument('--project', type=Path, action='append', default=[])
    parser.add_argument('--registry', type=Path, default=Path(__file__).parent / '.local' / 'projects.json')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--ready-file', type=Path)
    parser.add_argument('--checkpoint-dir', type=Path, default=Path(__file__).parent / '.local/checkpoints')
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
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
    class MonitoredClient(ExternalWorkerClient):
        def _consume(self, event, topic, *arguments):
            try:
                super()._consume(event, topic, *arguments)
            except BaseException:
                traceback.print_exc()
                with initialization_lock:
                    failed.set()
                    remove_ready()

    failed = threading.Event()
    initialized = set()
    initialization_lock = threading.Lock()
    client = MonitoredClient(host, auth=auth)
    acquire_jobs = client._restClient.acquire_jobs

    def monitored_acquire(topic, *arguments, **keywords):
        result = acquire_jobs(topic, *arguments, **keywords)
        with initialization_lock:
            initialized.add(topic)
        return result

    # 官方 subscribe 只启动线程；首轮拉取成功才能证明认证、连接及订阅初始化成功。
    client._restClient.acquire_jobs = monitored_acquire
    request = client._restClient.request_session.request
    def bounded_request(*arguments, **keywords):
        keywords.setdefault('timeout', min(args.timeout, 30))
        return request(*arguments, **keywords)
    client._restClient.request_session.request = bounded_request
    class WorkerSessions(DurableSessionManager):
        stopping = False

        def get(self, *arguments, **keywords):
            with self.lock:
                if self.stopping:
                    raise RuntimeError('Worker is stopping / 工作进程正在停止')
                return super().get(*arguments, **keywords)

        def close(self, run_id=None):
            with self.lock:
                if run_id is None:
                    self.stopping = True
                super().close(run_id)

    sessions = WorkerSessions(args.timeout, args.checkpoint_dir, host + '\n' + manifest['version'])
    lease = None
    subscriptions = []
    ready_token = uuid.uuid4().hex
    ready_temporary = None

    def remove_ready():
        if args.ready_file:
            try:
                if json.loads(args.ready_file.read_text(encoding='utf-8')).get('token') == ready_token:
                    args.ready_file.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass

    atexit.register(remove_ready)
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    def checkpoint(run_id, marker, value):
        from flowable_bridge import engine_request
        engine_request('/process-api/runtime/process-instances/' + run_id + '/variables',
                       json.dumps([{'name': marker, 'type': 'json' if isinstance(value, dict) else 'string',
                                    'value': value}]).encode())
    try:
        automatic = {topic: binding for topic, binding in manifest['bindings'].items() if binding.get('module')}
        lease = WorkerLease(host, automatic)
        resolved = {topic: select_project(binding, projects, registered) for topic, binding in automatic.items()}
        for topic, binding in automatic.items():
            subscriptions.append(client.subscribe(
                topic, make_callback(binding, sessions, resolved[topic], checkpoint),
                lock_duration=f'PT{max(300, math.ceil(args.timeout) + 60)}S', wait_period_seconds=1))
        deadline = time.monotonic() + min(args.timeout, 60)
        while True:
            if failed.is_set() or any(not item.thread.is_alive() for item in subscriptions):
                raise RuntimeError('Worker subscription failed / 工作进程订阅失败')
            with initialization_lock:
                complete = len(initialized) == len(automatic)
            if complete:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Worker subscription initialization timed out / 工作进程订阅初始化超时')
            failed.wait(0.05)
        if args.ready_file:
            args.ready_file.parent.mkdir(parents=True, exist_ok=True)
            ready_temporary = args.ready_file.with_name(args.ready_file.name + '.' + ready_token + '.tmp')
            ready_temporary.write_text(json.dumps({'pid': os.getpid(), 'token': ready_token,
                                                  'version': manifest.get('version'),
                                                  'topics': sorted(automatic)}), encoding='utf-8')
            with initialization_lock:
                if failed.is_set():
                    raise RuntimeError('Worker subscription failed / 工作进程订阅失败')
                ready_temporary.replace(args.ready_file)
        print('Subscribed: ' + ', '.join(automatic), flush=True)
        while True:
            if failed.wait(10) or any(not item.thread.is_alive() for item in subscriptions):
                raise RuntimeError('Worker subscription stopped / 工作进程订阅已停止')
            with sessions.lock:
                runs = set(sessions.known_runs)
            for run_id in runs:
                try:
                    response = requests.get(host.rstrip('/') + '/process-api/runtime/process-instances/' + run_id,
                                            auth=auth, timeout=5)
                    if response.status_code == 404:
                        sessions.finish(run_id)
                    elif response.ok:
                        pending = requests.get(host.rstrip('/') + '/diagnosis-api/instances/' + run_id + '/review/tasks', auth=auth, timeout=5)
                        jobs = requests.get(host.rstrip('/') + '/external-job-api/jobs', params={'processInstanceId': run_id, 'size': 1}, auth=auth, timeout=5)
                        if pending.ok and pending.json().get('tasks') and jobs.ok and jobs.json().get('total') == 0:
                            sessions.suspend(run_id)
                except requests.RequestException:
                    # 引擎暂时断开不代表流程结束，保留人工等待中的实例。
                    pass
    except KeyboardInterrupt:
        pass
    finally:
        remove_ready()
        if ready_temporary:
            try:
                ready_temporary.unlink(missing_ok=True)
            except OSError:
                traceback.print_exc()
        # 先禁止新会话并通知订阅停止，避免已在途的拉取请求在清理期间再创建业务进程。
        for subscription in subscriptions:
            subscription.event.set()
        try:
            sessions.close()
        finally:
            try:
                for subscription in subscriptions:
                    subscription.unsubscribe(timeout=35)
            finally:
                try:
                    client._restClient.request_session.close()
                finally:
                    if lease:
                        lease.close()


if __name__ == '__main__':
    main()
