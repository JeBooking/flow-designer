"""电源、通信、传感器与压力示例；设备数据和动作均为明确的模拟。"""
import asyncio
from diagnostic_demo.api import plot


def chart_result(values, title, threshold, **result):
    path, svg = plot(values, title=title, threshold=threshold)
    return dict(result, data=values, chart=path, chartSvg=svg)


def voltage(scenario):
    samples = {'normal': [24.1, 24.0, 23.9, 24.1], 'recover': [21.5, 21.2, 21.4, 21.6],
               'severe': [17.2, 18.1, 17.8, 18.0]}[scenario]
    return chart_result(samples, 'Supply voltage (V), lower limit', 22,
                        minimum=min(samples), abnormal=min(samples) < 22)


def voltage_conclusion(reading):
    return {'text': 'Undervoltage' if reading['abnormal'] else 'Supply voltage normal',
            'abnormal': reading['abnormal'], 'minimum': reading['minimum']}


def reseat_power(reading):
    recovered = reading['minimum'] >= 20
    return {'mode': 'simulation', 'performed': reading['abnormal'], 'recovered': recovered,
            'next': 'V_solved' if recovered else 'V_escalate'}


async def check_link(context, scenario):
    await asyncio.sleep(0)
    attempt = context.get('LinkCheck', {}).get('attempt', 0) + 1
    connected = scenario == 'normal' or (scenario == 'recover' and attempt >= 3)
    next_flow = 'L_ready' if connected else ('L_retry' if attempt < 3 else 'L_escalate')
    return chart_result([0] * (attempt - 1) + [int(connected)], 'Connection availability', 0.5,
                        attempt=attempt, connected=connected, next=next_flow)


def reset_link():
    return {'mode': 'simulation', 'action': 'Reset simulated communication channel'}


def link_conclusion(reading):
    return {'text': 'Connection established', 'attempts': reading['attempt']}


def acknowledge_link(conclusion):
    return {'confirmed': True, 'attempts': conclusion['attempts']}


def compare_sensors(scenario, source_label):
    a = [40, 41, 40, 42]
    b = [40.5, 41.2, 40.4, 42.1]
    if scenario in ('sensor-a', 'severe'):
        a = [value + 8 for value in a]
    elif scenario == 'sensor-b':
        b = [value + 7 for value in b]
    delta = [abs(left - right) for left, right in zip(a, b)]
    next_flow = 'S_channel_a' if scenario in ('sensor-a', 'severe') else ('S_channel_b' if scenario == 'sensor-b' else 'S_normal')
    return chart_result(delta, 'Sensor difference (C)', 3, a=a, b=b, next=next_flow,
                        source=source_label, abnormal=max(delta) > 3)


def analyze_channel(reading, channel):
    values = reading['a' if channel == 'A' else 'b']
    return {'channel': channel, 'mean': sum(values) / len(values), 'abnormal': reading['abnormal']}


def sensor_conclusion(context):
    analysis = context.get('SensorA') or context.get('SensorB')
    return {'text': 'Inspect sensor ' + analysis['channel'] if analysis else 'Sensors agree',
            'channel': analysis['channel'] if analysis else None}


def calibrate_sensor(conclusion, scenario):
    return {'mode': 'simulation', 'channel': conclusion['channel'],
            'next': 'S_escalate' if scenario == 'severe' else 'S_solved'}


def pressure(scenario):
    values = [9.5, 9.8, 9.6, 9.7]
    return chart_result(values, 'Pressure before recovery (bar)', 8, abnormal=True, scenario=scenario)


def pressure_conclusion(reading):
    return {'text': 'Pressure exceeds limit', 'peak': max(reading['data'])}


def vent_pressure(conclusion):
    return {'mode': 'simulation', 'vented': True, 'previousPeak': conclusion['peak']}


def reset_controller(vent):
    if not vent['vented']:
        raise ValueError('Vent before resetting controller')
    return {'mode': 'simulation', 'reset': True}


def analyze_pressure(reading, reset, scenario):
    if not reset['reset']:
        raise ValueError('Reset has not completed')
    samples = {'stable': [7, 6, 5, 4], 'leak': [7, 8, 9, 10], 'unknown': [7, 6, 7, 6]}[scenario]
    next_flow = {'stable': 'P_solved', 'leak': 'P_escalate', 'unknown': 'P_jump'}[scenario]
    return chart_result(samples, 'Pressure after recovery (bar)', 8, next=next_flow,
                        initialPeak=max(reading['data']))


def pressure_handoff(analysis):
    return {'status': 'handoff_requested', 'target': 'pressure-regulator-diagnosis',
            'evidence': analysis['data']}
