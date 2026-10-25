"""验证诊断分组编译与自动参数匹配，不需要启动 Java 或连接设备。"""
import json
from pathlib import Path
import sys
import types
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, b, f
from flowable_worker import execute, decision_branch, automatic_arguments

root = ET.Element(b('definitions'), {'targetNamespace': 'regression'})
process = ET.SubElement(root, b('process'), {'id': 'Grouped'})
ET.SubElement(process, b('startEvent'), {'id': 'Start'})
ET.SubElement(process, b('task'), {'id': 'Inspect', f('diagnosisKind'): 'investigation',
    f('humanDecision'): 'true', f('observation'): 'data', f('acquisition'): 'read',
    f('assessment'): 'check', f('referenceImage'): 'data:image/png;base64,AAAA'})
for key in ('A', 'B', 'C', 'D'):
    ET.SubElement(process, b('task'), {'id': key, 'name': key,
        f('diagnosisKind'): 'conclusion'})
    ET.SubElement(process, b('task'), {'id': key + 'Action', f('diagnosisKind'): 'remediation',
        f('pythonModule'): 'example', f('pythonFunction'): 'act', f('humanDecision'): 'true'})
ET.SubElement(process, b('task'), {'id': 'Solved', 'name': '问题解决', f('diagnosisKind'): 'problemSolved'})
def flow(id, source, target, branch=None):
    attrs = {'id': id, 'sourceRef': source, 'targetRef': target}
    if branch: attrs[f('diagnosisBranch')] = branch
    return ET.SubElement(process, b('sequenceFlow'), attrs)
flow('StartFlow', 'Start', 'Inspect')
for key, branch in zip(('A', 'B', 'C', 'D'), ('yes', 'yes', 'no', 'no')):
    flow('To' + key, 'Inspect', key, branch)
    flow(key + 'Run', key, key + 'Action')
    flow(key + 'Done', key + 'Action', 'Solved')
bundle = compile_workflow(ET.tostring(root, encoding='unicode'))
compiled = ET.fromstring(bundle['files']['workflow.bpmn20.xml'])
manifest = json.loads(bundle['files']['bindings.json'])
assert len(compiled.findall('.//' + b('inclusiveGateway'))) == 1
for key, branch in zip(('A', 'B', 'C', 'D'), ('yes', 'yes', 'no', 'no')):
    expression = compiled.find(f'.//{b("sequenceFlow")}[@id="To{key}"]/{b("conditionExpression")}').text
    assert '"' + branch + '"' in expression
assert list(manifest['reviews']) == ['Inspect']
assert {option['id'] for option in manifest['reviews']['Inspect']['options']} == {'yes', 'no'}
assert all(not value['humanDecision'] for value in manifest['bindings'].values() if value['kind'] != 'investigation')
invalid = flow('Forbidden', 'Inspect', 'AAction', 'yes')
try:
    compile_workflow(ET.tostring(root, encoding='unicode'))
except ValueError as error:
    assert 'rules' in str(error)
else:
    raise AssertionError('Investigation-to-remediation accepted')
process.remove(invalid)

module = types.ModuleType('parameter_regression')
exec('''
def no_io(): pass
def defaults(lay=None): return lay
def positional(voltage, /, *, limit=20): return voltage > limit
async def inspect(voltage): return voltage > 20
''', module.__dict__)
sys.modules[module.__name__] = module
def binding(function, kind='remediation'):
    return {'module': module.__name__, 'function': function, 'kind': kind,
            'outgoing': ['a', 'b'], 'branches': {'a': 'yes', 'b': 'no'} if kind == 'investigation' else {}}
assert execute(binding('no_io'), {}) is None
assert execute(binding('defaults'), {}) is None
assert execute(binding('defaults'), {'lay': 'fixture'}) == 'fixture'
assert execute(binding('positional'), {'Read': {'voltage': 24}}) is True
assert execute(binding('inspect', 'investigation'), {'voltage': 24}) is True
assert decision_branch(False, {}) == 'no'
assert decision_branch({'next': 'b'}, binding('inspect', 'investigation')) == 'no'
for variables, message in [({}, 'Missing'), ({'A': {'voltage': 1}, 'B': {'voltage': 2}}, 'Ambiguous')]:
    try:
        execute(binding('inspect', 'investigation'), variables)
    except ValueError as error:
        assert message in str(error)
    else:
        raise AssertionError('Unresolved parameter accepted')
assert automatic_arguments(module.positional, {}, {'voltage': 0}) == ([0], {})
print('PASS: grouped Yes/No Flowable compilation, merge terminals, action-only binding, connection rejection, automatic parameters, async/void/default/positional interfaces, missing/ambiguous data')
