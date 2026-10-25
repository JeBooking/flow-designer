"""验证参考文件边界和 Windows 启动分支；不会打开任何外部软件。"""
import base64
import json
from pathlib import Path
import sys
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import reference_files as files
from server import create_server

uri = 'data:application/octet-stream;base64,' + base64.b64encode(b'hello').decode()
assert files.parse_reference_file(uri) == ('application/octet-stream', b'hello')
assert files.parse_reference_file('data:text/plain;base64,') == ('text/plain', b'')
for invalid in ['data:text/html,hello', 'data:text/plain;base64,AA=', 'data:text/plain;base64,AB==', 'data:text/plain;base64,!!!!']:
    try:
        files.parse_reference_file(invalid)
        raise AssertionError(invalid)
    except ValueError:
        pass
with patch.object(files, 'MAX_BYTES', 1):
    try:
        files.parse_reference_file(uri)
        raise AssertionError('oversized file accepted')
    except ValueError:
        pass
for name in ['../bad.txt', r'C:\bad.txt', 'bad:name.txt', 'CON.txt', 'bad.', 'bad/thing']:
    try:
        files.open_reference_file({'name': name, 'dataUri': uri})
        raise AssertionError(name)
    except ValueError:
        pass
with patch.object(files.os, 'startfile') as start, patch.object(files, 'choose_application') as choose:
    assert files.launch_reference(Path('sample.txt')) == 'default'
    start.assert_called_once()
    choose.assert_not_called()
for code in (1155, 31):
    failure = OSError('no association')
    failure.winerror = code
    with patch.object(files.os, 'startfile', side_effect=failure), patch.object(files, 'choose_application') as choose:
        assert files.launch_reference(Path('sample.unknown')) == 'chooser'
        choose.assert_called_once()
with patch.object(files.os, 'startfile') as start, patch.object(files, 'choose_application') as choose:
    for extension in files.CHOOSER_EXTENSIONS:
        assert files.launch_reference(Path('sample' + extension)) == 'chooser'
    start.assert_not_called()
    assert choose.call_count == len(files.CHOOSER_EXTENSIONS)
with patch.object(files.subprocess, 'Popen') as launch:
    files.choose_application(Path('sample.any'))
    arguments = launch.call_args
    assert arguments.kwargs == {'shell': False}
    assert arguments.args[0][0].endswith('rundll32.exe')
with patch.object(files, 'launch_reference', return_value='default') as launch:
    assert files.open_reference_file({'name': 'notes.xyz', 'dataUri': uri})['ok']
    stored = launch.call_args.args[0]
    assert stored.name == 'notes.xyz' and stored.read_bytes() == b'hello'
    assert Path(files._STORE.name) in stored.parents

with tempfile.TemporaryDirectory() as directory:
    server = create_server(0, Path(directory) / 'projects.json')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f'http://127.0.0.1:{server.server_port}/api/reference-files/open'
    try:
        with patch.object(files, 'launch_reference', return_value='chooser'):
            request = Request(endpoint, data=json.dumps({'name': 'notes.xyz', 'dataUri': uri}).encode(), headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                assert json.load(response) == {'ok': True, 'openedWith': 'chooser'}
        request.add_header('Origin', 'https://untrusted.example')
        try:
            urlopen(request)
            raise AssertionError('untrusted origin accepted')
        except HTTPError as error:
            assert error.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
print('Reference-file data, path, mocked launcher and trusted-origin checks passed')
