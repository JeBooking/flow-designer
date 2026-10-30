"""对实际排图暴露的主题稳定性、条件与 ID 边界执行回归检查。"""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow, b, f
from verification_fixtures import review_workflow

xml = review_workflow('BoundaryVerification', 'boundary_fixture', 'inspect')

def manifest(root):
    return json.loads(compile_workflow(ET.tostring(root, encoding='unicode'))['files']['bindings.json'])

original = manifest(ET.fromstring(xml))
root = ET.fromstring(xml)
root.find('.//' + b('task')).set('name', 'Renamed / 修改名称')
root.find('.//' + b('task')).set(f('assessment'), 'Changed instructions / 修改说明')
process = root.find(b('process'))
process[:] = list(reversed(process))
ET.indent(root, space='    ')
assert manifest(root)['version'] == original['version'], 'Cosmetic edits invalidated worker topics'
assert set(manifest(root)['bindings']) == set(original['bindings']), 'Cosmetic edits changed worker topics'
root = ET.fromstring(xml)
task = root.find('.//' + b('task'))
task.set(f('pythonArguments'), '{"scenario":"new-input"}')
assert manifest(root)['version'] != original['version']
task.set(f('pythonArguments'), '{ }')
assert manifest(root) == original, 'JSON formatting changed worker topics'

def reject(change):
    root = ET.fromstring(xml)
    change(root)
    try:
        manifest(root)
    except ValueError:
        return
    raise AssertionError('Invalid executable diagram was accepted')

reject(lambda root: root.find('.//' + b('task')).set('id', 'Start'))
reject(lambda root: root.find('.//' + b('sequenceFlow')).attrib.pop('id'))
reject(lambda root: root.find('.//' + b('sequenceFlow')).set('id', 'Inspect'))
reject(lambda root: root.find('.//' + b('task')).set('default', 'F_conclusion'))
reject(lambda root: ET.SubElement(root.find('.//' + b('sequenceFlow')), b('conditionExpression')))
reject(lambda root: root.find('.//' + b('task')).set(f('pythonArguments'), '{"value":NaN}'))
print('PASS: cosmetic/serialization changes preserve topics; binding changes version topics; invalid IDs/conditions/nonfinite JSON rejected')
