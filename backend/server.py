"""本机 Python 项目接入服务；仅标准库，默认监听 127.0.0.1。"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlparse, unquote
import uuid
from flowable_bridge import compile_workflow, deploy, engine_request
from execution_manager import ExecutionManager
from reference_files import open_reference_file
from python_sessions import SessionManager

ROOT = Path(__file__).resolve().parent.parent
WORKER = Path(__file__).with_name('worker.py')


class Registry:
    def __init__(self, file, timeout=120):
        self.file = Path(file)
        self.timeout = timeout
        self.lock = threading.RLock()
        self.sessions = SessionManager(timeout)
        self.debug_sessions = {}
        self.projects = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {}

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.projects, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.file)

    def run(self, project, operation, **arguments):
        if operation == 'call':
            with self.lock:
                session_id = arguments.pop('sessionId', None)
                if session_id:
                    entry = self.debug_sessions.get(session_id)
                    if not entry or entry[0] != project['id']:
                        raise ValueError('Debug session lost / 调试会话已丢失，请重置后重试')
                    session = entry[2]
                else:
                    run_id = 'debug:' + uuid.uuid4().hex
                    session = self.sessions.get(run_id, project)
                    self.debug_sessions[session.id] = (project['id'], run_id, session)
            return session.call({'operation': 'debug', **arguments})
        with tempfile.TemporaryDirectory(prefix='diagnostic-interface-') as directory:
            result_file = Path(directory) / 'result.json'
            completed = subprocess.run(
                [project['python'], '-X', 'utf8', str(WORKER), str(result_file)],
                input=json.dumps({**project, **arguments, 'operation': operation}),
                text=True, encoding='utf-8', errors='replace', capture_output=True,
                cwd=project['path'], timeout=self.timeout,
                env={**os.environ, 'PYTHONUTF8': '1'},
            )
            if not result_file.exists():
                raise RuntimeError(f'Python exited ({completed.returncode}): {completed.stderr or completed.stdout}')
            result = json.loads(result_file.read_text(encoding='utf-8'))
            result['stdout'] += completed.stdout
            result['stderr'] += completed.stderr
            return result

    def register(self, data):
        path = Path(str(data.get('path', ''))).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError('Project path must be a directory')
        module = str(data.get('module', '')).strip()
        if not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', module):
            raise ValueError('Use an importable module name, for example plotting.api')
        factory = str(data.get('factory') or '').strip()
        if factory and not all(part.isidentifier() and not part.startswith('_') for part in factory.split('.')):
            raise ValueError('Use a public class or factory name / 请填写公开的类或工厂函数名')
        project = {'id': uuid.uuid4().hex, 'name': str(data.get('name') or path.name),
                   'path': str(path), 'module': module,
                   'factory': factory,
                   'python': str(data.get('python') or sys.executable)}
        result = self.run(project, 'discover')
        if not result['ok']:
            return result
        project.update(interfaces=result['interfaces'], moduleFile=result['moduleFile'],
                       initParameters=result.get('initParameters', []))
        with self.lock:
            # 同一入口重新登记即刷新接口，保留平台 ID。
            existing = next((p for p in self.projects.values()
                             if p['path'] == project['path'] and p['module'] == module
                             and p.get('factory', '') == factory), None)
            if existing:
                project['id'] = existing['id']
                self.close_debug(project['id'])
            self.projects[project['id']] = project
            self.save()
        return {**result, 'project': project}

    def close_debug(self, project_id=None, session_id=None):
        with self.lock:
            keys = [key for key, entry in self.debug_sessions.items()
                    if (project_id is None or entry[0] == project_id)
                    and (session_id is None or key == session_id)]
            for key in keys:
                _, run_id, _ = self.debug_sessions.pop(key)
                self.sessions.close(run_id)

    def get(self, project_id):
        with self.lock:
            if project_id not in self.projects:
                raise KeyError('Unknown project ID')
            return dict(self.projects[project_id])


def paged_history(path):
    """保留 Flowable data 协议，超过安全页数时明确失败而非静默丢历史。"""
    result = None
    data = []
    seen = set()
    for _ in range(1000):
        page = engine_request(path + '&start=' + str(len(data)) + '&size=200')
        items = page.get('data')
        if not isinstance(items, list):
            raise RuntimeError('Invalid Flowable history page / Flowable 历史分页格式错误')
        if result is None:
            result = dict(page)
        if not items:
            total = page.get('total')
            if isinstance(total, int) and len(data) < total:
                raise RuntimeError('Incomplete Flowable history / Flowable 历史分页未返回完整数据')
            break
        signature = json.dumps(items, sort_keys=True)
        if signature in seen:
            raise RuntimeError('Flowable history pagination did not advance / Flowable 历史分页未前进')
        seen.add(signature)
        data.extend(items)
        total = page.get('total')
        if isinstance(total, int) and len(data) >= total:
            break
    else:
        raise RuntimeError('Flowable history exceeds pagination limit / Flowable 历史超过分页安全上限')
    result.update(data=data, start=0, size=len(data), total=len(data))
    return result


def make_handler(registry, executions):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT / 'dist'), **kwargs)

        def reply(self, value, status=200):
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

        def trusted(self):
            # 本机代码执行入口只接受本机 Host 与开发/本机页面来源。
            host = urlparse('http://' + self.headers.get('Host', '')).hostname
            origin = self.headers.get('Origin')
            return host in ('localhost', '127.0.0.1') and (
                not origin or origin in self.server.allowed_origins)

        def do_GET(self):
            if not self.trusted():
                self.reply({'error': 'Origin or host is not allowed'}, 403)
                return
            route = urlparse(self.path).path
            if route == '/api/health':
                engine_url = urlparse(os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080'))
                self.reply({'ok': True, 'service': 'diagnosis-backend',
                            'flowableUrl': engine_url._replace(netloc=engine_url.netloc.rsplit('@', 1)[-1]).geturl()})
                return
            if route == '/api/projects':
                with registry.lock:
                    self.reply({'projects': list(registry.projects.values())})
                return
            if route.startswith('/api/flowable/history/'):
                run_id = route.rsplit('/', 1)[-1]
                if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
                    self.reply({'error': 'Invalid run ID'}, 400)
                    return
                try:
                    failed = paged_history('/process-api/management/deadletter-jobs?processInstanceId=' + run_id)['data']
                    for job in failed:
                        if job.get('exceptionMessage'):
                            job['traceback'] = engine_request('/process-api/management/deadletter-jobs/' + job['id'] + '/exception-stacktrace', as_text=True)
                    pending_reviews = engine_request('/diagnosis-api/instances/' + run_id + '/review/tasks')['tasks']
                    self.reply({'process': engine_request('/process-api/history/historic-process-instances/' + run_id),
                        'failures': failed,
                        'variables': paged_history('/process-api/history/historic-variable-instances?processInstanceId=' + run_id),
                        'activities': paged_history('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&sort=startTime&order=asc'),
                        'pendingReviews': pending_reviews,
                        'review': pending_reviews[0] if pending_reviews else {'pending': False}})
                except RuntimeError as error:
                    self.reply({'error': str(error)}, 502)
                return
            if route.startswith('/api/'):
                self.reply({'error': 'Not found'}, 404)
                return
            if route in ('/', '/vue-bpmn-designer', '/vue-bpmn-designer/'):
                self.path = '/index.html'
            elif route.startswith('/vue-bpmn-designer/'):
                self.path = route[len('/vue-bpmn-designer'):]
            target = (ROOT / 'dist' / unquote(self.path).lstrip('/')).resolve()
            if ROOT / 'dist' not in target.parents:
                self.reply({'error': 'Invalid path'}, 403)
                return
            super().do_GET()

        def do_POST(self):
            if not self.trusted():
                self.reply({'error': 'Origin or host is not allowed'}, 403)
                return
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.reply({'error': 'application/json required'}, 415)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                large_routes = {'/api/reference-files/open', '/api/flowable/compile', '/api/flowable/start'}
                limit = 70 * 1024 * 1024 if urlparse(self.path).path in large_routes else 8 * 1024 * 1024
                if not 0 < size <= limit:
                    raise ValueError(f'Total request must be between 1 byte and {limit // (1024 * 1024)} MB; reduce the combined reference file size')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Request must be a JSON object')
                parts = urlparse(self.path).path.strip('/').split('/')
                if parts == ['api', 'reference-files', 'open']:
                    result = open_reference_file(data)
                elif parts == ['api', 'flowable', 'compile']:
                    result = {'ok': True, **compile_workflow(data['xml'])}
                elif len(parts) == 4 and parts[:2] == ['api', 'flowable'] and parts[2] == 'review':
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', parts[3]):
                        raise ValueError('Invalid run ID')
                    try:
                        result = engine_request('/diagnosis-api/instances/' + parts[3] + '/review', json.dumps(data).encode())
                    except RuntimeError as error:
                        # 保留引擎的冲突状态，界面才能刷新已结束或被其他窗口提交的任务。
                        if isinstance(error.__cause__, HTTPError) and error.__cause__.code == 409:
                            self.reply({'ok': False, 'error': str(error)}, 409)
                            return
                        raise
                elif parts == ['api', 'flowable', 'start']:
                    variables = data.get('variables', {})
                    if not isinstance(variables, dict):
                        raise ValueError('Variables must be an object')
                    # 在启动协调器和部署之前拒绝不可序列化或非有限数值变量。
                    json.dumps(variables, allow_nan=False)
                    compiled = compile_workflow(data['xml'])
                    executions.ensure_worker(compiled['files']['bindings.json'])
                    if executions.closing.is_set():
                        raise RuntimeError('Backend is closing / 后端正在关闭')
                    deployment = deploy(compiled['files']['workflow.bpmn20.xml'])
                    definitions = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])
                    definition_id = definitions['data'][0]['id']
                    # JSON 变量可保存嵌套结果，工作进程与网关共享同一流程实例。
                    run = engine_request('/process-api/runtime/process-instances', json.dumps({
                        'processDefinitionId': definition_id,
                        'variables': [{'name': key, 'type': 'json', 'value': value} for key, value in variables.items()]
                    }).encode())
                    result = {'ok': True, 'run': run, 'files': compiled['files']}
                elif parts == ['api', 'projects']:
                    result = registry.register(data)
                elif len(parts) == 5 and parts[:2] == ['api', 'projects'] and parts[3:] == ['sessions', 'close']:
                    registry.get(parts[2])
                    registry.close_debug(parts[2], data.get('sessionId'))
                    result = {'ok': True}
                elif len(parts) == 4 and parts[:2] == ['api', 'projects']:
                    project = registry.get(parts[2])
                    if parts[3] == 'call':
                        result = registry.run(project, 'call', function=data['function'],
                                              args=data.get('args', []), kwargs=data.get('kwargs', {}),
                                              inputs=data.get('inputs', {}), sessionId=data.get('sessionId'))
                    elif parts[3] == 'refresh':
                        result = registry.register(project)
                    elif parts[3] == 'remove':
                        with registry.lock:
                            registry.close_debug(project['id'])
                            del registry.projects[project['id']]
                            registry.save()
                        result = {'ok': True}
                    else:
                        self.reply({'error': 'Not found'}, 404)
                        return
                else:
                    self.reply({'error': 'Not found'}, 404)
                    return
                self.reply(result, 200 if result.get('ok') else 422)
            except (ValueError, TypeError, KeyError, OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as error:
                self.reply({'ok': False, 'error': f'{type(error).__name__}: {error}'}, 400)

    return Handler


def create_server(port=8765, registry_file=None, timeout=120, origins=None):
    registry = Registry(registry_file or ROOT / 'backend' / '.local' / 'projects.json', timeout)
    executions = ExecutionManager(registry, timeout)
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(registry, executions))
    close_server = server.server_close
    def close():
        # 先禁止新协调器并终止自有业务进程，避免等待 HTTP 线程时遗留后台执行。
        try:
            executions.close()
        finally:
            try:
                registry.close_debug()
            finally:
                close_server()
    server.server_close = close
    server.allowed_origins = set(origins or []) | {
        f'http://{host}:{p}' for host in ('localhost', '127.0.0.1')
        for p in (5173, 5174, server.server_port)}
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local Python project integration')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--registry', type=Path, default=None)
    parser.add_argument('--origin', action='append', default=[])
    args = parser.parse_args()
    server = create_server(args.port, registry_file=args.registry, timeout=args.timeout, origins=args.origin)
    print(f'Python backend: http://127.0.0.1:{server.server_port}/vue-bpmn-designer/', flush=True)
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
