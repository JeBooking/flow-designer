"""复用电压图布局，演示带 Python 和纯人工两种判断节点。"""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f

directory = ROOT / 'src/views/ProcessDesigner/examples'
root = ET.fromstring((directory / 'voltage-diagnosis.bpmn').read_text(encoding='utf-8'))
process = root.find(b('process'))
process.set('id', 'HumanVoltageDiagnosis')
process.set('name', '人工判断与回退 / Human decisions and rechecks')
for plane in root.iter('{http://www.omg.org/spec/BPMN/20100524/DI}BPMNPlane'):
    plane.set('bpmnElement', 'HumanVoltageDiagnosis')
for task in process.findall(b('task')):
    if task.get('id') in ('Voltage', 'VoltageConclusion', 'Reseat'):
        task.set(f('humanDecision'), 'true')
    if task.get('id') == 'VoltageConclusion':
        for field in ('pythonModule', 'pythonFunction', 'pythonArguments'):
            task.attrib.pop(f(field), None)
ET.indent(root, space='  ')
(directory / 'human-decision.bpmn').write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True))
