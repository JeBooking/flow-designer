"""生成八个独立的人工处理覆盖示例；只写本生成器拥有的 BPMN 文件。"""

import argparse
import base64
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).absolute().parent.parent
OUTPUT = ROOT / 'backend' / 'examples' / 'manual_handling_project' / 'diagrams'
GENERATOR = 'manual-handling-examples-generator'
NAMESPACES = {
    'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
    'flowable': 'http://flowable.org/bpmn',
    'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
    'dc': 'http://www.omg.org/spec/DD/20100524/DC',
    'di': 'http://www.omg.org/spec/DD/20100524/DI',
}
for prefix, namespace in NAMESPACES.items():
    ET.register_namespace(prefix, namespace)

REFERENCE = (
    '电压参考 / Voltage reference\n'
    '标准：电压 >= 22 V 请选择是（yes）；电压 < 22 V 请选择否（no）。\n'
    'Rule: select yes for voltage >= 22 V; select no for voltage < 22 V.\n'
    '默认示例证据为 21.2 V；启动输入改变时按实际返回证据判断，人工接管时请核对后确认。\n'
    'The default example evidence is 21.2 V; if start input changes, decide from the actual '
    'returned evidence and review it before confirming human selection.\n'
    '所有值均为示例输入；流程不读取或控制设备。\n'
    'All values are example inputs; this workflow neither reads nor controls equipment.\n'
)

# 各案例只改变排查绑定和接管方式；普通异常案例明确保留失败语义。
CASES = (
    ('01-automatic.bpmn', 'Automatic', '自动判断 / Automatic decision',
     'automatic_decision', False,
     'Python 根据电压直接返回 yes/no，不请求人工。默认 21.2 V 返回 no。 / '
     'Python returns yes/no from voltage without human review. The default 21.2 V returns no.'),
    ('02-manual-only.bpmn', 'ManualOnly', '纯人工判断 / Manual decision only',
     None, True,
     '排查不绑定 Python；直接由人工核对示例电压 21.2 V 并选择 yes/no。 / '
     'No Python binding: a person reviews the example voltage of 21.2 V and selects yes/no.'),
    ('03-bound-manual.bpmn', 'BoundManual', '采集后人工判断 / Evidence then human decision',
     'collect_evidence', True,
     'Python 只返回电压证据，不返回分支；humanDecision=true 请求人工选择。 / '
     'Python returns voltage evidence without a branch; humanDecision=true requests human selection.'),
    ('04-base-fallback.bpmn', 'BaseFallback', '基类回退人工 / Base class fallback',
     'base_fallback', False,
     '判断组件基类未实现判断，组件协议返回人工接管请求；人工开关保持关闭。 / '
     'The decision component base class has no decision implementation and returns a human '
     'review request through its protocol; the manual switch remains off.'),
    ('05-decorator-fallback.bpmn', 'DecoratorFallback', '装饰器回退人工 / Decorator fallback',
     'decorator_fallback', False,
     '判断装饰器捕获判断函数内的 NotImplementedError 并请求人工；不是普通函数异常回退。 / '
     'The decision decorator converts its decision function\'s NotImplementedError into a human '
     'review request; this applies to the decorated decision protocol.'),
    ('06-explicit-review.bpmn', 'ExplicitReview', '显式请求人工 / Explicit human review',
     'explicit_review', False,
     'Python 显式调用 human_judgment 返回人工接管请求；无需开启人工开关。 / '
     'Python explicitly calls human_judgment to request human review with the manual switch off.'),
    ('07-ordinary-error.bpmn', 'OrdinaryError', '普通函数失败 / Ordinary function failure',
     'ordinary_unimplemented', False,
     '预期失败：普通函数主动抛出 NotImplementedError，执行应报错，不能自动转人工或继续。 / '
     'Expected failure: an ordinary function raises NotImplementedError. Execution must fail '
     'without automatic human review or continuation.'),
    ('08-empty-result.bpmn', 'EmptyResult', '空返回值失败 / Empty result failure',
     'empty_decision', False,
     '预期失败：排查函数仅执行 pass，返回 None；返回值非法，应报错而不能自动转人工或继续。 / '
     'Expected failure: the investigation function only executes pass and returns None. This '
     'invalid result must fail without automatic human review or continuation.'),
)


def tag(prefix, name):
    return '{' + NAMESPACES[prefix] + '}' + name


def flowable(name):
    return tag('flowable', name)


def generate(case):
    _, suffix, title, function, human, behavior = case
    process_id = 'ManualHandling_' + suffix
    root = ET.Element(tag('bpmn', 'definitions'), {
        'id': 'Definitions_' + process_id,
        'targetNamespace': 'http://diagnosis.local/examples/manual-handling',
        'exporter': GENERATOR,
        'exporterVersion': '1',
    })
    process = ET.SubElement(root, tag('bpmn', 'process'), {
        'id': process_id, 'name': title, 'isExecutable': 'false',
        flowable('diagnosisMode'): 'serial',
    })
    diagram = ET.SubElement(root, tag('bpmndi', 'BPMNDiagram'), {'id': process_id + '_diagram'})
    plane = ET.SubElement(diagram, tag('bpmndi', 'BPMNPlane'), {
        'id': process_id + '_plane', 'bpmnElement': process_id,
    })
    nodes = (
        ('Start', None, '开始 / Start',
         '仅进入当前案例的单个排查。 / Enter this case\'s single investigation.',
         (70, 162, 36, 36)),
        ('Check', 'investigation', '电压 ≥ 22 V？\nVoltage ≥ 22 V?', behavior,
         (180, 130, 220, 100)),
        ('Conclusion', 'conclusion', '电压达标\nVoltage meets threshold',
         '是分支：电压大于或等于 22 V，形成文字结论；本节点不执行 Python 或人工判断。 / '
         'Yes branch: voltage is at least 22 V. This text conclusion runs no Python or human decision.',
         (490, 130, 220, 100)),
        ('Record', 'remediation', '记录示例结果\nRecord example result',
         '仅进入示例记录步骤，record_result() 返回 None；不写文件、不触设备。 / '
         'Run the example recording step only: record_result() returns None without file or device I/O.',
         (790, 130, 220, 100)),
        ('Solved', 'problemSolved', '问题解决\nProblem solved',
         '示例是分支已完成；不表示已修复任何实际设备。 / '
         'The example yes branch is complete; no actual equipment repair is implied.',
         (1090, 130, 220, 100)),
        ('Escalation', 'escalation', '上升处理\nEscalation',
         '否分支：电压低于 22 V，将证据交给上级复核；此节点是最终节点。 / '
         'No branch: voltage is below 22 V. Hand the evidence to escalation review at this terminal node.',
         (490, 350, 220, 100)),
    )
    elements = {}
    for node_id, kind, name, detail, bounds in nodes:
        attributes = {'id': node_id, 'name': name, flowable('detailText'): detail}
        if kind:
            attributes[flowable('diagnosisKind')] = kind
        element = ET.SubElement(process, tag('bpmn', 'task' if kind else 'startEvent'), attributes)
        elements[node_id] = element
        if node_id == 'Check':
            content = {
                'humanDecision': 'true' if human else 'false',
                'observation': '观察示例电压是否达到 22 V；默认 21.2 V，单位 V。 / '
                               'Observe whether the example voltage reaches 22 V; default: 21.2 V.',
                'acquisition': (
                    '只使用示例输入，不读取设备。Python 函数默认使用 21.2 V；'
                    '启动输入中的同名 voltage 可覆盖默认值，例如 voltage=24。 / '
                    'Use example input only, without reading equipment. Python defaults to 21.2 V; '
                    'the matching voltage start input overrides this default, for example voltage=24.'
                    if function else
                    '纯人工案例没有 Python 绑定；直接使用节点说明中的固定示例值 21.2 V，'
                    '不读取设备或启动电压输入。 / '
                    'This manual-only case has no Python binding. Use the fixed 21.2 V example '
                    'from the node instructions without reading equipment or voltage start input.'
                ),
                'assessment': '电压 ≥ 22 V 选是（yes），进入结论；电压 < 22 V 选否（no），进入上升。'
                              '默认 21.2 V 对应否。' + behavior + ' / '
                              'Select yes for voltage ≥ 22 V to reach the conclusion; select no for '
                              'voltage < 22 V to escalate. The default 21.2 V corresponds to no.',
                'referenceImage': 'data:text/plain;base64,'
                                  + base64.b64encode(REFERENCE.encode('utf-8')).decode('ascii'),
                'referenceImageName': 'reference.txt',
            }
            if function:
                # 空映射允许运行时按同名启动输入注入 voltage，否则保留函数默认值。
                content.update(pythonModule='manual_handling', pythonFunction=function,
                               pythonArguments='{}')
            for key, value in content.items():
                element.set(flowable(key), value)
        elif node_id == 'Conclusion':
            element.set(flowable('conclusionText'), detail)
        elif node_id == 'Record':
            element.set(flowable('pythonModule'), 'manual_handling')
            element.set(flowable('pythonFunction'), 'record_result')
            element.set(flowable('pythonArguments'), '{}')
        shape = ET.SubElement(plane, tag('bpmndi', 'BPMNShape'), {
            'id': node_id + '_di', 'bpmnElement': node_id,
        })
        ET.SubElement(shape, tag('dc', 'Bounds'), {
            key: str(value) for key, value in zip(('x', 'y', 'width', 'height'), bounds)
        })
        if node_id == 'Start':
            label = ET.SubElement(shape, tag('bpmndi', 'BPMNLabel'))
            ET.SubElement(label, tag('dc', 'Bounds'), {
                'x': '48', 'y': '205', 'width': '80', 'height': '22',
            })

    # 否分支先向下再向右，避免穿过是分支上的结论或处置节点。
    edges = (
        ('Start_Check', 'Start', 'Check', None, [(106, 180), (180, 180)], None),
        ('Check_Yes', 'Check', 'Conclusion', 'yes', [(400, 180), (490, 180)], (405, 148)),
        ('Check_No', 'Check', 'Escalation', 'no',
         [(290, 230), (290, 400), (490, 400)], (300, 285)),
        ('Conclusion_Record', 'Conclusion', 'Record', None, [(710, 180), (790, 180)], None),
        ('Record_Solved', 'Record', 'Solved', None, [(1010, 180), (1090, 180)], None),
    )
    for flow_id, source, target, branch, points, label_position in edges:
        attributes = {'id': flow_id, 'sourceRef': source, 'targetRef': target}
        if branch:
            attributes.update(name=branch)
            attributes[flowable('diagnosisBranch')] = branch
            attributes[flowable('diagnosisOrder')] = '0' if branch == 'yes' else '1'
        ET.SubElement(process, tag('bpmn', 'sequenceFlow'), attributes)
        ET.SubElement(elements[source], tag('bpmn', 'outgoing')).text = flow_id
        ET.SubElement(elements[target], tag('bpmn', 'incoming')).text = flow_id
        edge = ET.SubElement(plane, tag('bpmndi', 'BPMNEdge'), {
            'id': flow_id + '_di', 'bpmnElement': flow_id,
        })
        for x, y in points:
            ET.SubElement(edge, tag('di', 'waypoint'), {'x': str(x), 'y': str(y)})
        if label_position:
            label = ET.SubElement(edge, tag('bpmndi', 'BPMNLabel'))
            ET.SubElement(label, tag('dc', 'Bounds'), {
                'x': str(label_position[0]), 'y': str(label_position[1]),
                'width': '80', 'height': '22',
            })
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true',
                        help='Regenerate only files marked as owned by this generator')
    args = parser.parse_args()
    targets = [(OUTPUT / case[0], generate(case)) for case in CASES]
    # 写入前检查全部目标，避免发现已有用户文件时只更新了一部分案例。
    for path, _ in targets:
        if not path.exists():
            continue
        if not args.force:
            parser.error('Refusing to overwrite existing file: ' + str(path) + '; use --force')
        try:
            owned = ET.parse(path).getroot().get('exporter') == GENERATOR
        except (ET.ParseError, OSError):
            owned = False
        if not owned:
            parser.error('Refusing to overwrite a file not owned by this generator: ' + str(path))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path, payload in targets:
        path.write_bytes(payload)
        print(path.relative_to(ROOT))


if __name__ == '__main__':
    main()
