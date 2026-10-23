"""生成包含所有诊断节点、Python 绑定及可视布局的编辑器示例。"""
import base64
from pathlib import Path
import struct
import sys
import zlib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import BPMN, FLOWABLE, b, f

DC = 'http://www.omg.org/spec/DD/20100524/DC'
DI = 'http://www.omg.org/spec/DD/20100524/DI'
BPMNDI = 'http://www.omg.org/spec/BPMN/20100524/DI'


def reference():
    width, height = 240, 120
    pixels = bytearray([255] * width * height * 3)
    for x in range(10, 230):
        for y, color in ((45, (220, 38, 38)), (90 - int(x / 12), (37, 99, 235))):
            offset = (y * width + x) * 3
            pixels[offset:offset + 3] = bytes(color)
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    raw = b''.join(b'\x00' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
    return 'data:image/png;base64,' + base64.b64encode(png).decode()


def create():
    import json
    definitions = ET.Element(b('definitions'), {'id': 'Definitions_Demo', 'targetNamespace': 'http://diagnosis.local/example'})
    process = ET.SubElement(definitions, b('process'), {'id': 'DiagnosticDemo', 'name': '温度诊断 / Temperature diagnosis', 'isExecutable': 'false'})
    diagram = ET.SubElement(definitions, '{' + BPMNDI + '}BPMNDiagram', {'id': 'Diagram_Demo'})
    plane = ET.SubElement(diagram, '{' + BPMNDI + '}BPMNPlane', {'id': 'Plane_Demo', 'bpmnElement': 'DiagnosticDemo'})
    nodes = [
        ('Start', None, '开始 / Start', None, {}, 40, 210),
        ('Inspect', 'investigation', '采集温度、绘图并判断', 'inspect_temperature', {'scenario': '$scenario'}, 140, 190),
        ('Action', 'investigationAction', '执行风扇自检（模拟）', 'machine_action', {}, 330, 50),
        ('Recheck', 'investigation', '自检后重新采集并判断', 'recheck', {'action': '$Action'}, 510, 50),
        ('Conclusion', 'conclusion', '得到温度诊断结论', 'conclude', {'context': '$'}, 520, 240),
        ('Repair', 'remediation', '按结论采取恢复措施（模拟）', 'recover', {'scenario': '$scenario', 'conclusion': '$Conclusion'}, 740, 240),
        ('Solved', 'problemSolved', '问题解决', None, {}, 1020, 90),
        ('Deep', 'deepDiagnosis', '分析温度趋势及均值', 'deep_diagnosis', {'inspection': '$Inspect'}, 1000, 240),
        ('Escalation', 'escalation', '上升', None, {}, 1230, 340),
        ('Jump', 'jump', '交接至冷却子系统链路', 'handoff', {'inspection': '$Inspect'}, 1000, 440),
    ]
    positions = {}
    elements = {}
    for node_id, kind, name, function, kwargs, x, y in nodes:
        width, height = (36, 36) if kind is None else (145, 80)
        positions[node_id] = (x, y, width, height)
        node = ET.SubElement(process, b('startEvent' if kind is None else 'task'), {'id': node_id, 'name': name})
        elements[node_id] = node
        if kind:
            node.set(f('diagnosisKind'), kind)
        if function:
            node.set(f('pythonModule'), 'diagnostic_demo.api')
            node.set(f('pythonFunction'), function)
            node.set(f('pythonArguments'), json.dumps(kwargs))
        if kind == 'investigation':
            for key, value in {'observation': '温度采样值（摄氏度）', 'acquisition': '示例生成模拟温度数据；实际工程替换为采集接口',
                'assessment': '任一采样值大于 70°C 则判为异常；蓝线为采样趋势，红线为阈值', 'referenceImage': reference()}.items():
                node.set(f(key), value)
        if kind == 'conclusion':
            node.set(f('conclusionText'), '根据阈值判断温度正常或异常；本结论不意味着诊断已经结束')
        if kind == 'investigationAction':
            node.set(f('actionText'), '模拟执行风扇自检以推动后续诊断；不控制真实机台，不在这里进行现象判断')
        shape = ET.SubElement(plane, '{' + BPMNDI + '}BPMNShape', {'id': node_id + '_di', 'bpmnElement': node_id})
        ET.SubElement(shape, '{' + DC + '}Bounds', {'x': str(x), 'y': str(y), 'width': str(width), 'height': str(height)})
    edges = [('F_start', 'Start', 'Inspect', ''), ('F_action', 'Inspect', 'Action', 'action 场景'),
        ('F_conclusion', 'Inspect', 'Conclusion', '无需自检'), ('F_recheck', 'Action', 'Recheck', ''),
        ('F_checked', 'Recheck', 'Conclusion', ''), ('F_repair', 'Conclusion', 'Repair', ''),
        ('F_solved', 'Repair', 'Solved', '正常或恢复成功'), ('F_deep', 'Repair', 'Deep', '需要深度诊断'),
        ('F_escalate', 'Repair', 'Escalation', '严重异常'), ('F_jump', 'Repair', 'Jump', '交接其他链路'),
        ('F_deep_end', 'Deep', 'Escalation', '转交专家')]
    for flow_id, source, target, name in edges:
        ET.SubElement(process, b('sequenceFlow'), {'id': flow_id, 'sourceRef': source, 'targetRef': target, 'name': name})
        ET.SubElement(elements[source], b('outgoing')).text = flow_id
        ET.SubElement(elements[target], b('incoming')).text = flow_id
        edge = ET.SubElement(plane, '{' + BPMNDI + '}BPMNEdge', {'id': flow_id + '_di', 'bpmnElement': flow_id})
        sx, sy, sw, sh = positions[source]
        tx, ty, tw, th = positions[target]
        points = [(sx + sw, sy + sh / 2), ((sx + sw + tx) / 2, sy + sh / 2), ((sx + sw + tx) / 2, ty + th / 2), (tx, ty + th / 2)]
        if flow_id == 'F_checked':
            points = [(sx + sw / 2, sy + sh), (sx + sw / 2, ty)]
        elif flow_id == 'F_escalate':
            points = [(sx + sw / 2, sy + sh), (sx + sw / 2, 380), (tx, 380)]
        for px, py in points:
            ET.SubElement(edge, '{' + DI + '}waypoint', {'x': str(px), 'y': str(py)})
    path = ROOT / 'src/views/ProcessDesigner/examples/diagnostic-demo.bpmn'
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(definitions)
    path.write_text(ET.tostring(definitions, encoding='unicode', xml_declaration=True), encoding='utf-8')
    return path


if __name__ == '__main__':
    print(create())
