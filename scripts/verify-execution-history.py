"""真实引擎验证增量历史、可变活动、画布关联和服务重启后的游标重置。"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import engine_request, compile_workflow, deploy, b, f
from python_sessions import stop_process
from server import create_server
from verification_fixtures import deployed_workflow, review_workflow, post, review, choose, ended, wait_for


def verify():
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    previous = os.environ.get('FLOWABLE_URL')
    os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory(prefix='incremental-history-') as directory:
        directory = Path(directory)
        with (directory / 'engine.log').open('w', encoding='utf-8') as log:
            engine = subprocess.Popen(['java', '-jar', str(ROOT / 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
                f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:incrementalhistory;DB_CLOSE_DELAY=-1'],
                cwd=directory, stdout=log, stderr=log,
                **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
            server = thread = None
            try:
                def ready():
                    try:
                        return engine_request('/process-api/management/engine')
                    except RuntimeError:
                        return None
                wait_for(ready)
                server = create_server(0, registry_file=directory / 'registry.json')
                server.RequestHandlerClass.log_message = lambda *args: None
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()

                def request(path, value=None):
                    data = json.dumps(value).encode() if value is not None else None
                    with urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/flowable/' + path,
                        data, {'Content-Type': 'application/json'}), timeout=30) as response:
                        raw = response.read()
                        return json.loads(raw), len(raw)

                xml = review_workflow('IncrementalHistoryVerification')
                with deployed_workflow(xml) as definition:
                    instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                        'variables': [{'name': 'large', 'type': 'json', 'value': {'data': 'x' * (2 * 1024 * 1024)}}]
                            + [{'name': 'input_' + str(index), 'type': 'integer', 'value': index} for index in range(601)]})['id']
                    path = 'history/' + instance
                    full, full_bytes = request(path)
                    assert full['reset'] and full['pendingReviews']
                    assert len({row['id'] for row in full['variables']['data']}) == len(full['variables']['data'])
                    assert len([row for row in full['variables']['data'] if row['variable']['name'].startswith('input_')]) == 601
                    cursor = full['cursor']
                    stable, stable_bytes = request(path + '?cursor=' + cursor)
                    assert not stable['changed'] and not stable['reset']
                    assert not stable['variables']['data'] and not stable['activities']['data']
                    assert 'pendingReviews' not in stable
                    assert stable_bytes < full_bytes / 100
                    match, _ = request('match/' + instance, {'xml': xml})
                    assert match['matches']
                    mismatch, _ = request('match/' + instance, {'xml': xml.replace('IncrementalHistoryVerification', 'DifferentDefinition')})
                    assert not mismatch['matches']
                    post('/process-api/runtime/process-instances/' + instance + '/variables', [{'name': 'counter', 'type': 'integer', 'value': 1}])
                    changed, _ = request(path + '?cursor=' + cursor)
                    assert changed['changed'] and not changed['reset']
                    assert any(row['variable']['name'] == 'counter' and row['variable']['value'] == 1 for row in changed['variables']['data'])
                    assert all(row['variable']['name'] != 'large' for row in changed['variables']['data'])
                    cursor = changed['cursor']
                    engine_request('/process-api/runtime/process-instances/' + instance + '/variables/counter',
                        json.dumps({'name': 'counter', 'type': 'integer', 'value': 2}).encode(), method='PUT')
                    updated, _ = request(path + '?cursor=' + cursor)
                    assert any(row['variable']['name'] == 'counter' and row['variable']['value'] == 2 for row in updated['variables']['data'])
                    counter_id = next(row['id'] for row in updated['variables']['data'] if row['variable']['name'] == 'counter')
                    engine_request('/process-api/runtime/process-instances/' + instance + '/variables/counter', method='DELETE')
                    removed, _ = request(path + '?cursor=' + updated['cursor'])
                    assert counter_id in removed['removedVariableIds']
                    choose(instance, review(instance), next='yes')
                    moved, _ = request(path + '?cursor=' + removed['cursor'])
                    assert any(activity['activityId'] == 'Inspect' and activity['endTime'] for activity in moved['activities']['data'])
                    assert moved['pendingReviews'][0]['nodeId'] == 'Repair'
                    choose(instance, review(instance), next='ok')
                    wait_for(lambda: ended(instance))
                    final, _ = request(path + '?cursor=' + moved['cursor'])
                    assert final['process']['endTime'] and final['pendingReviews'] == []
                    # 新服务没有前一进程的游标缓存，必须回落全量，不能把旧游标当成空增量。
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)
                    server = create_server(0, registry_file=directory / 'registry.json')
                    server.RequestHandlerClass.log_message = lambda *args: None
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    recovered, _ = request(path + '?cursor=' + final['cursor'])
                    assert recovered['reset'] and recovered['variables']['data']
                    # 旧部署把元数据放在 documentation，新的历史接口不能收窄兼容范围。
                    legacy = compile_workflow(xml.replace('IncrementalHistoryVerification', 'LegacyMetadataVerification'))
                    legacy_root = ET.fromstring(legacy['files']['workflow.bpmn20.xml'])
                    legacy_process = legacy_root.find(b('process'))
                    extensions = legacy_process.find(b('extensionElements'))
                    extension = extensions.find(f('diagnosticExecution'))
                    metadata = json.loads(extension.get('value'))
                    metadata['nodes'] = {key: {name: value[name] for name in ('id', 'name', 'kind', 'outgoing')} for key, value in metadata['nodes'].items()}
                    metadata['bindings'] = {key: {'nodeId': value['nodeId']} for key, value in metadata['bindings'].items()}
                    for value in metadata['reviews'].values():
                        value.pop('instructions', None)
                    extensions.remove(extension)
                    documentation = ET.Element(b('documentation'))
                    documentation.text = json.dumps({'diagnosticExecution': metadata}, separators=(',', ':'))
                    assert len(documentation.text) <= 2000
                    legacy_process.insert(0, documentation)
                    deployment = deploy(ET.tostring(legacy_root, encoding='unicode'))
                    definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
                    legacy_instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
                    old, _ = request('history/' + legacy_instance)
                    assert old['version'] == metadata['version'] and old['nodes'] and old['pendingReviews']
                    with deployed_workflow(xml.replace('IncrementalHistoryVerification', 'DeletedDefinitionVerification')) as definition:
                        archived = post('/process-api/runtime/process-instances', {'processDefinitionId': definition})['id']
                        choose(archived, review(archived), next='yes')
                        choose(archived, review(archived), next='ok')
                        wait_for(lambda: ended(archived))
                        deployment_id = engine_request('/process-api/repository/process-definitions/' + definition)['deploymentId']
                        engine_request('/process-api/repository/deployments/' + deployment_id, method='DELETE')
                        archived_state, _ = request('history/' + archived)
                        assert archived_state['process']['endTime'] and archived_state['activities']['data'] and archived_state['variables']['data']
                    try:
                        request('history/missing-instance')
                    except HTTPError as error:
                        assert error.code == 404
                    else:
                        raise AssertionError('Missing instance accepted')
                    print(json.dumps({'passed': True, 'fullBytes': full_bytes, 'unchangedBytes': stable_bytes,
                        'checks': ['large values omitted', 'variable revisions', 'activity completion',
                                   'task transitions', 'definition match', 'ended history', 'backend restart cursor reset', 'legacy metadata']}, ensure_ascii=False))
            except BaseException:
                log.flush()
                print((directory / 'engine.log').read_text(encoding='utf-8', errors='replace')[-10000:])
                raise
            finally:
                if server:
                    server.shutdown()
                    server.server_close()
                if thread:
                    thread.join(timeout=5)
                stop_process(engine)
                if previous is None:
                    os.environ.pop('FLOWABLE_URL', None)
                else:
                    os.environ['FLOWABLE_URL'] = previous


if __name__ == '__main__':
    verify()
