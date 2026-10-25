"""使用独立端口和内存数据库验证真实引擎，不触碰用户已有实例。"""
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, deploy, engine_request

with socket.socket() as available:
    available.bind(('127.0.0.1', 0))
    port = available.getsockname()[1]
os.environ['FLOWABLE_URL'] = f'http://127.0.0.1:{port}'
def post(path, data):
    return engine_request(path, json.dumps(data).encode())

with tempfile.TemporaryDirectory(prefix='diagnosis-parallel-') as directory:
    with open(Path(directory) / 'engine.log', 'w', encoding='utf-8') as log:
        jar = next((ROOT / 'flowable-runtime/target').glob('*.jar'))
        engine = subprocess.Popen(['java', '-jar', str(jar),
            f'--server.port={port}', '--spring.datasource.url=jdbc:h2:mem:parallelcheck;DB_CLOSE_DELAY=-1'],
            cwd=directory, stdout=log, stderr=log)
        worker = None
        try:
            for _ in range(100):
                if engine.poll() is not None:
                    raise RuntimeError(Path(directory, 'engine.log').read_text(encoding='utf-8', errors='replace'))
                try:
                    engine_request('/process-api/management/engine')
                    break
                except RuntimeError:
                    time.sleep(0.3)
            else:
                raise RuntimeError('Local test engine did not start')
            xml = (ROOT / 'src/views/ProcessDesigner/examples/parallel-dependencies.bpmn').read_text(encoding='utf-8')
            bundle = compile_workflow(xml)
            bindings = Path(directory, 'bindings.json')
            bindings.write_text(bundle['files']['bindings.json'], encoding='utf-8')
            worker = subprocess.Popen([str(ROOT / 'backend/.local/venv/Scripts/python.exe'), '-X', 'utf8',
                str(ROOT / 'backend/flowable_worker.py'), str(bindings), '--project',
                str(ROOT / 'backend/examples/diagnostic_demo')], cwd=directory, stdout=log, stderr=log)
            deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
            definition = engine_request('/process-api/repository/process-definitions?deploymentId=' + deployment['id'])['data'][0]['id']
            for scenario, expected, absent in [('normal', {'PowerCheck', 'AAction', 'BAction'}, {'CAction', 'DAction'}),
                                               ('unavailable', {'CAction', 'DAction'}, {'PowerCheck', 'AAction', 'BAction'})]:
                instance = post('/process-api/runtime/process-instances', {'processDefinitionId': definition,
                    'variables': [{'name': 'scenario', 'type': 'string', 'value': scenario}]})['id']
                for _ in range(100):
                    state = engine_request('/process-api/history/historic-process-instances/' + instance)
                    if state.get('endTime'): break
                    time.sleep(0.3)
                else:
                    raise RuntimeError('Process did not finish: ' + Path(directory, 'engine.log').read_text(encoding='utf-8'))
                visits = engine_request('/process-api/history/historic-activity-instances?processInstanceId=' + instance + '&size=1000')['data']
                actual = {visit['activityId'] for visit in visits}
                assert expected <= actual and not absent & actual, (scenario, actual)
                assert sum(visit['activityId'] == 'Solved' for visit in visits) == 2
            print('PASS: real Flowable Yes/No fan-out, prerequisite checks, two terminal arrivals, automatic parameters and void actions')
        finally:
            if worker:
                worker.terminate()
                worker.wait(timeout=10)
            engine.terminate()
            engine.wait(timeout=10)
