"""生成结构各异的可执行诊断图；折线和标签分别设置，避免穿过节点。"""
import json
from pathlib import Path
import runpy
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import b, f

base = runpy.run_path(str(Path(__file__).with_name('create-diagnostic-demo.py')))
reference = base['reference']
DC, DI, BPMNDI = base['DC'], base['DI'], base['BPMNDI']


def node(node_id, kind, name, function, kwargs, x, y, description=''):
    return dict(id=node_id, kind=kind, name=name, function=function, kwargs=kwargs,
                x=x, y=y, description=description)


def write_example(filename, process_id, title, nodes, edges, subject, acquisition, assessment):
    root = ET.Element(b('definitions'), {'id': 'Definitions_' + process_id, 'targetNamespace': 'http://diagnosis.local/examples'})
    process = ET.SubElement(root, b('process'), {'id': process_id, 'name': title, 'isExecutable': 'false'})
    diagram = ET.SubElement(root, '{' + BPMNDI + '}BPMNDiagram', {'id': process_id + '_diagram'})
    plane = ET.SubElement(diagram, '{' + BPMNDI + '}BPMNPlane', {'id': process_id + '_plane', 'bpmnElement': process_id})
    elements, bounds = {}, {}
    for spec in nodes:
        kind, node_id = spec['kind'], spec['id']
        element = ET.SubElement(process, b('task' if kind else 'startEvent'), {'id': node_id, 'name': spec['name']})
        elements[node_id] = element
        if kind:
            element.set(f('diagnosisKind'), kind)
        if spec['function']:
            element.set(f('pythonModule'), 'diagnostic_demo.scenarios')
            element.set(f('pythonFunction'), spec['function'])
            element.set(f('pythonArguments'), json.dumps(spec['kwargs'], ensure_ascii=False))
        if kind == 'investigation':
            for key, value in {'observation': subject, 'acquisition': acquisition,
                               'assessment': assessment, 'referenceImage': reference()}.items():
                element.set(f(key), value)
        if kind == 'conclusion':
            element.set(f('conclusionText'), spec['description'])
        elif kind == 'investigationAction':
            element.set(f('actionText'), spec['description'])
        elif spec['description']:
            ET.SubElement(element, b('documentation')).text = spec['description']
        x, y = spec['x'], spec['y']
        width, height = (36, 36) if not kind else (170, 86)
        bounds[node_id] = (x, y, width, height)
        shape = ET.SubElement(plane, '{' + BPMNDI + '}BPMNShape', {'id': node_id + '_di', 'bpmnElement': node_id})
        ET.SubElement(shape, '{' + DC + '}Bounds', {key: str(value) for key, value in zip(('x', 'y', 'width', 'height'), (x, y, width, height))})
    for flow_id, source, target, label, waypoints in edges:
        ET.SubElement(process, b('sequenceFlow'), {'id': flow_id, 'sourceRef': source, 'targetRef': target, 'name': label})
        ET.SubElement(elements[source], b('outgoing')).text = flow_id
        ET.SubElement(elements[target], b('incoming')).text = flow_id
        edge = ET.SubElement(plane, '{' + BPMNDI + '}BPMNEdge', {'id': flow_id + '_di', 'bpmnElement': flow_id})
        if not waypoints:
            sx, sy, sw, sh = bounds[source]
            tx, ty, _, th = bounds[target]
            waypoints = [(sx + sw, sy + sh / 2), (tx, ty + th / 2)]
        for x, y in waypoints:
            ET.SubElement(edge, '{' + DI + '}waypoint', {'x': str(x), 'y': str(y)})
        if label:
            x1, y1 = waypoints[0]
            x2, y2 = waypoints[1]
            label_element = ET.SubElement(edge, '{' + BPMNDI + '}BPMNLabel')
            ET.SubElement(label_element, '{' + DC + '}Bounds', {'x': str((x1 + x2) / 2 - 40), 'y': str((y1 + y2) / 2 - 24), 'width': '80', 'height': '20'})
    ET.indent(root)
    path = ROOT / 'src/views/ProcessDesigner/examples' / filename
    path.write_text(ET.tostring(root, encoding='unicode', xml_declaration=True), encoding='utf-8')
    print(path.name)


def create():
    start = lambda y: node('Start', None, '开始', None, {}, 80, y + 25)
    solved = lambda x, y: node('Solved', 'problemSolved', '问题解决', None, {}, x, y)
    escalation = lambda x, y: node('Escalation', 'escalation', '上升', None, {}, x, y)
    write_example('voltage-diagnosis.bpmn', 'VoltageDiagnosis', '电源电压诊断', [
        start(200), node('Voltage', 'investigation', '读取电压并绘图', 'voltage', {'scenario': '$scenario'}, 190, 200),
        node('VoltageConclusion', 'conclusion', '判断供电是否正常', 'voltage_conclusion', {'reading': '$Voltage'}, 460, 200, '最低电压低于 22 V 为欠压，正常时确认无需处置。'),
        node('Reseat', 'remediation', '检查并复位供电连接（模拟）', 'reseat_power', {'reading': '$Voltage'}, 730, 200, '模拟检查连接；低于 20 V 时需要专家处理。'),
        solved(1010, 100), escalation(1010, 340)], [
        ('V_start', 'Start', 'Voltage', '', []), ('V_conclude', 'Voltage', 'VoltageConclusion', '', []),
        ('V_reseat', 'VoltageConclusion', 'Reseat', '', []),
        ('V_solved', 'Reseat', 'Solved', '恢复或正常', [(900, 225), (950, 225), (950, 143), (1010, 143)]),
        ('V_escalate', 'Reseat', 'Escalation', '无法恢复', [(900, 260), (970, 260), (970, 383), (1010, 383)])],
        '24 V 电源采样值，单位 V', '从模拟电源接口取得采样；可替换为实际采集工程。', '蓝线为电压；红线为 22 V 下限。任一点低于下限判定欠压。')

    write_example('communication-retry.bpmn', 'CommunicationRetry', '通信诊断：有上限的重试环', [
        start(260), node('LinkCheck', 'investigation', '异步检查连接并判断', 'check_link', {'context': '$', 'scenario': '$scenario'}, 190, 260),
        node('RetryAction', 'investigationAction', '复位通信通道（模拟）', 'reset_link', {}, 190, 60, '只执行模拟通道复位；随后回到排查节点判断连接，最多检查三次。'),
        node('LinkConclusion', 'conclusion', '连接恢复', 'link_conclusion', {'reading': '$LinkCheck'}, 490, 260, '连接已建立，记录成功前的检查次数。'),
        node('Acknowledge', 'remediation', '确认恢复并结束', 'acknowledge_link', {'conclusion': '$LinkConclusion'}, 770, 260),
        solved(1040, 260), escalation(490, 470)], [
        ('L_start', 'Start', 'LinkCheck', '', []),
        ('L_retry', 'LinkCheck', 'RetryAction', '未连接且不足三次', [(275, 260), (275, 146)]),
        ('L_reset', 'RetryAction', 'LinkCheck', '再次排查', [(190, 103), (150, 103), (150, 303), (190, 303)]),
        ('L_ready', 'LinkCheck', 'LinkConclusion', '连接成功', []),
        ('L_escalate', 'LinkCheck', 'Escalation', '三次仍失败', [(275, 346), (275, 513), (490, 513)]),
        ('L_confirm', 'LinkConclusion', 'Acknowledge', '', []), ('L_done', 'Acknowledge', 'Solved', '', [])],
        '通道连接状态及累计检查次数', '异步调用模拟连接接口；计数保存在 LinkCheck 流程变量中。', '蓝线取 0 表示失败、1 表示成功；红线为 0.5。失败三次后上升，禁止无限重试。')

    write_example('sensor-comparison.bpmn', 'SensorComparison', '双传感器差异分析与分支汇合', [
        start(250), node('ReadSensors', 'investigation', '比较两路传感器并绘图', 'compare_sensors', {'scenario': '$scenario', 'source_label': '$$sensor-input'}, 190, 250),
        node('SensorA', 'investigation', '分析传感器 A', 'analyze_channel', {'reading': '$ReadSensors', 'channel': 'A'}, 460, 70),
        node('SensorB', 'investigation', '分析传感器 B', 'analyze_channel', {'reading': '$ReadSensors', 'channel': 'B'}, 460, 450),
        node('SensorConclusion', 'conclusion', '汇总当前支路结论', 'sensor_conclusion', {'context': '$'}, 740, 250, '只读取实际执行的传感器分析结果；两路一致时直接确认一致。'),
        node('Calibrate', 'remediation', '校准或确认传感器（模拟）', 'calibrate_sensor', {'conclusion': '$SensorConclusion', 'scenario': '$scenario'}, 1030, 250),
        solved(1330, 100), escalation(1330, 440)], [
        ('S_start', 'Start', 'ReadSensors', '', []),
        ('S_channel_a', 'ReadSensors', 'SensorA', '疑似 A 偏移', [(360, 275), (410, 275), (410, 113), (460, 113)]),
        ('S_channel_b', 'ReadSensors', 'SensorB', '疑似 B 偏移', [(360, 310), (400, 310), (400, 493), (460, 493)]),
        ('S_normal', 'ReadSensors', 'SensorConclusion', '读数一致', []),
        ('S_a_join', 'SensorA', 'SensorConclusion', '', [(630, 113), (825, 113), (825, 250)]),
        ('S_b_join', 'SensorB', 'SensorConclusion', '', [(630, 493), (825, 493), (825, 336)]),
        ('S_calibrate', 'SensorConclusion', 'Calibrate', '', []),
        ('S_solved', 'Calibrate', 'Solved', '确认正常或已校准', [(1200, 275), (1260, 275), (1260, 143), (1330, 143)]),
        ('S_escalate', 'Calibrate', 'Escalation', '严重偏移', [(1200, 310), (1250, 310), (1250, 483), (1330, 483)])],
        '两路温度采样及对应差值', '调用模拟传感器采集接口。A/B 分析接口共享同一个已有工程。', '比较每对采样的绝对差值；差值超过 3°C 为不一致。参考图蓝线为差值、红线为上限。')

    write_example('pressure-recovery.bpmn', 'PressureRecovery', '压力诊断：连续处置、深度分析与交接', [
        start(250), node('PressureRead', 'investigation', '采集压力并判断', 'pressure', {'scenario': '$scenario'}, 190, 250),
        node('PressureConclusion', 'conclusion', '压力超限', 'pressure_conclusion', {'reading': '$PressureRead'}, 460, 250, '压力超过 8 bar，需要先泄压，再复位控制器。'),
        node('Vent', 'remediation', '先执行泄压（模拟）', 'vent_pressure', {'conclusion': '$PressureConclusion'}, 730, 250),
        node('Reset', 'remediation', '再复位控制器（模拟）', 'reset_controller', {'vent': '$Vent'}, 1000, 250),
        node('PressureDeep', 'deepDiagnosis', '绘图并分析恢复后趋势', 'analyze_pressure', {'reading': '$PressureRead', 'reset': '$Reset', 'scenario': '$scenario'}, 1270, 250),
        solved(1580, 70), escalation(1580, 270),
        node('PressureJump', 'jump', '交接调压阀诊断链路', 'pressure_handoff', {'analysis': '$PressureDeep'}, 1580, 470)], [
        ('P_start', 'Start', 'PressureRead', '', []), ('P_conclude', 'PressureRead', 'PressureConclusion', '', []),
        ('P_vent', 'PressureConclusion', 'Vent', '', []), ('P_reset', 'Vent', 'Reset', '', []),
        ('P_analyze', 'Reset', 'PressureDeep', '', []),
        ('P_solved', 'PressureDeep', 'Solved', '压力稳定', [(1440, 275), (1500, 275), (1500, 113), (1580, 113)]),
        ('P_escalate', 'PressureDeep', 'Escalation', '持续升压', [(1440, 293), (1510, 293), (1510, 313), (1580, 313)]),
        ('P_jump', 'PressureDeep', 'PressureJump', '需要其它链路', [(1440, 320), (1490, 320), (1490, 513), (1580, 513)])],
        '压力采样，单位 bar', '模拟采集压力；后续处置由独立业务函数提供。', '压力超过 8 bar 为超限；蓝线为压力，红线为阈值。处置后需再次绘图分析趋势。')


if __name__ == '__main__':
    create()
