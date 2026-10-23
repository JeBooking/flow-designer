"""本机 Python 项目接入服务；仅标准库，默认监听 127.0.0.1。"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote
import uuid
from flowable_bridge import compile_workflow, deploy, engine_request

ROOT = Path(__file__).resolve().parent.parent
WORKER = Path(__file__).with_name('worker.py')


class Registry:
    def __init__(self, file, timeout=120):
        self.file = Path(file)
        self.timeout = timeout
        self.lock = threading.RLock()
        self.projects = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {}

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.projects, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.file)

    def run(self, project, operation, **arguments):
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
        project = {'id': uuid.uuid4().hex, 'name': str(data.get('name') or path.name),
                   'path': str(path), 'module': module,
                   'python': str(data.get('python') or sys.executable)}
        result = self.run(project, 'discover')
        if not result['ok']:
            return result
        project.update(interfaces=result['interfaces'], moduleFile=result['moduleFile'])
        with self.lock:
            # 同一入口重新登记即刷新接口，保留平台 ID。
            existing = next((p for p in self.projects.values()
                             if p['path'] == project['path'] and p['module'] == module), None)
            if existing:
                project['id'] = existing['id']
            self.projects[project['id']] = project
            self.save()
        return {**result, 'project': project}

    def get(self, project_id):
        with self.lock:
            if project_id not in self.projects:
                raise KeyError('Unknown project ID')
            return dict(self.projects[project_id])


def make_handler(registry):
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
                    self.reply({'process': engine_request('/process-api/history/historic-process-instances/' + run_id),
                        'variables': engine_request('/process-api/history/historic-variable-instances?processInstanceId=' + run_id + '&size=200'),
                        'activities': engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + run_id + '&size=200&sort=startTime&order=asc'),
                        'review': engine_request('/diagnosis-api/instances/' + run_id + '/review')})
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
                if not 0 < size <= 8 * 1024 * 1024:
                    raise ValueError('Request must be between 1 byte and 8 MB')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Request must be a JSON object')
                parts = urlparse(self.path).path.strip('/').split('/')
                if parts == ['api', 'flowable', 'compile']:
                    result = {'ok': True, **compile_workflow(data['xml'])}
                elif len(parts) == 4 and parts[:2] == ['api', 'flowable'] and parts[2] == 'review':
                    if not re.fullmatch(r'[A-Za-z0-9_-]+', parts[3]):
                        raise ValueError('Invalid run ID')
                    result = engine_request('/diagnosis-api/instances/' + parts[3] + '/review', json.dumps(data).encode())
                elif parts == ['api', 'flowable', 'start']:
                    compiled = compile_workflow(data['xml'])
                    variables = data.get('variables', {})
                    if not isinstance(variables, dict):
                        raise ValueError('Variables must be an object')
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
                elif len(parts) == 4 and parts[:2] == ['api', 'projects']:
                    project = registry.get(parts[2])
                    if parts[3] == 'call':
                        result = registry.run(project, 'call', function=data['function'],
                                              args=data.get('args', []), kwargs=data.get('kwargs', {}))
                    elif parts[3] == 'refresh':
                        result = registry.register(project)
                    elif parts[3] == 'remove':
                        with registry.lock:
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
            except (ValueError, TypeError, KeyError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                self.reply({'ok': False, 'error': f'{type(error).__name__}: {error}'}, 400)

    return Handler


def create_server(port=8765, registry_file=None, timeout=120, origins=None):
    registry = Registry(registry_file or ROOT / 'backend' / '.local' / 'projects.json', timeout)
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(registry))
    server.allowed_origins = set(origins or []) | {
        f'http://{host}:{p}' for host in ('localhost', '127.0.0.1')
        for p in (5173, 5174, server.server_port)}
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Local Python project integration')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--origin', action='append', default=[])
    args = parser.parse_args()
    server = create_server(args.port, timeout=args.timeout, origins=args.origin)
    print(f'Python backend: http://127.0.0.1:{server.server_port}/vue-bpmn-designer/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
