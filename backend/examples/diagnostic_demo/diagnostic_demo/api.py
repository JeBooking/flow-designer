"""使用模拟温度数据完成真实绘图与阈值判断，不控制真实机台。"""
from pathlib import Path
import uuid

OUTPUT = Path(__file__).resolve().parent.parent / 'output'


def plot(values):
    points = ' '.join(f'{40 + index * 60},{240 - value * 2}' for index, value in enumerate(values))
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="300" viewBox="0 0 600 300">'
        '<rect width="600" height="300" fill="white"/>'
        '<text x="40" y="25" font-size="18">Temperature / threshold: 70 C</text>'
        '<path d="M40 40 V240 H560" fill="none" stroke="#475569"/>'
        '<path d="M40 100 H560" stroke="#dc2626" stroke-dasharray="6 4"/>'
        f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="3"/>'
        '<text x="40" y="280">Samples (simulated machine data)</text></svg>')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / (uuid.uuid4().hex + '.svg')
    path.write_text(svg, encoding='utf-8')
    return str(path), svg


def inspect_temperature(scenario='recover'):
    if scenario not in ('normal', 'recover', 'escalate', 'jump', 'action', 'severe'):
        raise ValueError('Unknown example scenario: ' + scenario)
    values = [40, 42, 43, 41, 40, 42, 41, 40] if scenario == 'normal' else [45, 52, 64, 75, 82, 85, 86, 88]
    path, svg = plot(values)
    return {'data': values, 'abnormal': max(values) > 70, 'chart': path, 'chartSvg': svg,
            'scenario': scenario, 'next': 'F_action' if scenario == 'action' else 'F_conclusion'}


def machine_action():
    return {'performed': True, 'mode': 'simulation', 'description': 'Simulated fan self-test; no real machine command sent'}


def recheck(action):
    if not action['performed']:
        raise ValueError('Self-test has not completed')
    values = [80, 78, 76, 74, 72, 71, 70, 69]
    path, svg = plot(values)
    return {'data': values, 'abnormal': max(values) > 70, 'chart': path, 'chartSvg': svg}


def conclude(context):
    inspection = context.get('Recheck', context['Inspect'])
    return {'text': 'Temperature above threshold' if inspection['abnormal'] else 'Temperature normal',
            'abnormal': inspection['abnormal']}


def recover(scenario, conclusion):
    next_flow = {'escalate': 'F_deep', 'jump': 'F_jump', 'severe': 'F_escalate'}.get(scenario, 'F_solved')
    return {'next': next_flow, 'mode': 'simulation', 'action': 'Simulated cooling reset' if conclusion['abnormal'] else 'No reset required',
            'recovered': next_flow == 'F_solved'}


def deep_diagnosis(inspection):
    average = sum(inspection['data']) / len(inspection['data'])
    return {'average': average, 'requiresSpecialist': inspection['abnormal']}


def handoff(inspection):
    # 跳转目标由业务工程负责交接；示例生成待交接记录，不假装执行了另一条流程。
    return {'status': 'handoff_requested', 'target': 'cooling-subsystem-diagnosis',
            'reason': 'Investigate cooling subsystem', 'abnormal': inspection['abnormal']}
