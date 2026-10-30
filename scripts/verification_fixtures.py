"""当前是/否分组协议的独立验证图，不修改用于迁移演示的旧示例。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from flowable_bridge import b, f, compile_workflow, deploy, engine_request
from python_sessions import stop_process

ROOT = Path(__file__).resolve().parents[1]


def post(path, value):
    return engine_request(path, json.dumps(value).encode())


def wait_for(callback):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        value = callback()
        if value:
            return value
        time.sleep(0.15)
    raise AssertionError('Timed out waiting for verification state')


def review(instance):
    tasks = engine_request('/diagnosis-api/instances/' + instance + '/review/tasks')['tasks']
    return tasks[0] if tasks else None


def choose(instance, task, **fields):
    return post('/diagnosis-api/instances/' + instance + '/review', {
        'action': 'confirm', 'taskId': task['taskId'], **fields})


def historic_values(instance):
    return {entry['variable']['name']: entry['variable']['value'] for entry in engine_request(
        '/process-api/history/historic-variable-instances?processInstanceId=' + instance + '&size=1000')['data']}


def ended(instance):
    return engine_request('/process-api/history/historic-process-instances/' + instance).get('endTime')


@contextmanager
def deployed_workflow(xml, sources=None):
    bundle = compile_workflow(xml)
    with tempfile.TemporaryDirectory(prefix='workflow-verification-') as directory:
        directory = Path(directory)
        for name, source in (sources or {}).items():
            (directory / name).write_text(source, encoding='utf-8')
        bindings = directory / 'bindings.json'
        bindings.write_text(bundle['files']['bindings.json'], encoding='utf-8')
        worker = None
        with (directory / 'worker.log').open('w', encoding='utf-8') as log:
            try:
                if sources:
                    worker = subprocess.Popen([sys.executable, '-u', str(ROOT / 'backend/flowable_worker.py'),
                        str(bindings), '--project', str(directory)], stdout=log, stderr=log,
                        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
                deployment = deploy(bundle['files']['workflow.bpmn20.xml'])
                yield engine_request('/process-api/repository/process-definitions?deploymentId='
                    + deployment['id'])['data'][0]['id']
            except BaseException:
                log.flush()
                print((directory / 'worker.log').read_text(encoding='utf-8', errors='replace')[-12000:])
                raise
            finally:
                stop_process(worker)


def review_workflow(process_id='ReviewVerification', module='', function='', action_mode='manual'):
    root = ET.Element(b('definitions'), {'targetNamespace': 'verification'})
    process = ET.SubElement(root, b('process'), {'id': process_id})
    ET.SubElement(process, b('startEvent'), {'id': 'Start'})
    attributes = {'id': 'Inspect', f('diagnosisKind'): 'investigation',
                  f('observation'): 'Samples', f('acquisition'): 'Simulated data',
                  f('assessment'): 'Check samples', f('referenceImage'): 'data:text/plain;base64,AAAA'}
    if module:
        attributes.update({f('pythonModule'): module, f('pythonFunction'): function})
    else:
        attributes[f('humanDecision')] = 'true'
    ET.SubElement(process, b('task'), attributes)
    ET.SubElement(process, b('task'), {'id': 'Conclusion', 'name': 'Diagnostic conclusion',
                  f('diagnosisKind'): 'conclusion', f('detailText'): 'Observed condition'})
    ET.SubElement(process, b('task'), {'id': 'Repair', f('diagnosisKind'): 'remediation',
                  f('actionMode'): action_mode, f('detailText'): 'Simulated repair'})
    ET.SubElement(process, b('task'), {'id': 'Solved', f('diagnosisKind'): 'problemSolved'})
    ET.SubElement(process, b('task'), {'id': 'Escalation', f('diagnosisKind'): 'escalation'})
    for key, source, target, branch in [
        ('Begin', 'Start', 'Inspect', None), ('Yes', 'Inspect', 'Conclusion', 'yes'),
        ('No', 'Inspect', 'Escalation', 'no'), ('Act', 'Conclusion', 'Repair', None),
        ('Done', 'Repair', 'Solved', None),
    ]:
        fields = {'id': key, 'sourceRef': source, 'targetRef': target}
        if branch:
            fields[f('diagnosisBranch')] = branch
        ET.SubElement(process, b('sequenceFlow'), fields)
    return ET.tostring(root, encoding='unicode')
