"""从 HTTP 登记外部工程、发现接口并调用真实 Python 函数。"""
import json
from pathlib import Path
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from server import create_server


with tempfile.TemporaryDirectory(prefix='python-project-test-') as temporary:
    directory = Path(temporary)
    registry_file = directory / 'registry.json'
    server = create_server(0, registry_file=registry_file, timeout=5)
    server.RequestHandlerClass.log_message = lambda *args: None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api/projects'

    def request(path='', data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            with urlopen(req) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    try:
        status, response = request(data={'path': 'backend/examples/sample_project', 'module': 'sample_plot'})
        assert status == 200, response
        project = response['project']
        assert {entry['name'] for entry in project['interfaces']} == {'summarize', 'draw_chart'}
        project_id = project['id']
        status, response = request(f'/{project_id}/call', {'function': 'summarize', 'args': [[2, 4, 6]]})
        assert status == 200 and response['result'] == {'count': 3, 'mean': 4}, response
        chart = directory / 'chart.svg'
        status, response = request(f'/{project_id}/call', {'function': 'draw_chart', 'args': [[10, 20]], 'kwargs': {'output': str(chart)}})
        assert status == 200 and chart.exists() and '<polyline' in chart.read_text(), response
        assert request(f'/{project_id}/call', {'function': '_private'})[0] == 422
        assert request(f'/{project_id}/call', {'function': 'summarize', 'args': {}})[0] == 422
        assert request(f'/{project_id}/refresh', {})[1]['project']['id'] == project_id
        assert request(data={'path': str(directory), 'module': 'os'})[0] == 422
        assert request(data={'path': str(directory), 'module': 'no_such_module'})[0] == 422
        assert request(data={}, origin='https://external.example')[0] == 403
        # 两个目录有同名模块时，必须各自加载，且下一次调用反映源码改动。
        for name, value in [('one', 11), ('two', 22)]:
            project_dir = directory / name
            project_dir.mkdir()
            (project_dir / 'api.py').write_text(f'print("loaded")\ndef value():\n    return {value}\n', encoding='utf-8')
            status, registered = request(data={'path': str(project_dir), 'module': 'api'})
            assert status == 200, registered
            status, called = request('/' + registered['project']['id'] + '/call', {'function': 'value'})
            assert status == 200 and called['result'] == value and 'loaded' in called['stdout'], called
        second = create_server(0, registry_file=registry_file)
        second.server_close()
        assert len(json.loads(registry_file.read_text(encoding='utf-8'))) == 3
        assert request(f'/{project_id}/remove', {})[0] == 200
        assert len(request()[1]['projects']) == 2
        assert (ROOT / 'backend/examples/sample_project/sample_plot/__init__.py').exists()
        print('PASS: registration, public API discovery, execution, SVG output, refresh, isolation, persistence, unregister, import failures and origin restriction')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
