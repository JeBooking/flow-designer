"""人工接管覆盖示例：只使用传入电压，不采集设备数据或执行设备动作。"""

from typing import Literal, NoReturn, TypedDict

from diagnostic_components import DecisionComponent, HumanDecisionRequest, decision, human_judgment
__diagnosis_stateless__ = True


__all__ = [
    'automatic_decision',
    'collect_evidence',
    'base_fallback',
    'decorator_fallback',
    'explicit_review',
    'ordinary_unimplemented',
    'empty_decision',
    'record_result',
]


class _Evidence(TypedDict):
    voltage: float
    threshold: Literal[22]
    unit: Literal['V']


class _AutomaticResult(_Evidence):
    next: Literal['yes', 'no']


_INSTRUCTIONS = (
    '请根据电压证据确认：电压是否大于或等于 22 V？是请选择 yes，否请选择 no。 '
    'Confirm from the voltage evidence: is the voltage greater than or equal to 22 V? '
    'Select yes if it is, otherwise select no.'
)


def _evidence(voltage: float) -> _Evidence:
    return {'voltage': voltage, 'threshold': 22, 'unit': 'V'}


def automatic_decision(voltage: float = 21.2) -> _AutomaticResult:
    return {**_evidence(voltage), 'next': 'yes' if voltage >= 22 else 'no'}


def collect_evidence(voltage: float = 21.2) -> _Evidence:
    # 不给出分支，让 humanDecision=true 的流程负责请求人工选择。
    return _evidence(voltage)


def base_fallback(voltage: float = 21.2) -> HumanDecisionRequest:
    # 保留基类未实现的判断，以展示组件协议内的人工回退。
    return DecisionComponent().run(_evidence(voltage), instructions=_INSTRUCTIONS)


@decision(instructions=_INSTRUCTIONS)
def _unimplemented_decision(data: _Evidence) -> NoReturn:
    # 证据作为第一个参数传入，使装饰器回退时能够保留判断依据。
    raise NotImplementedError('Intentional decorated decision fallback')


def decorator_fallback(voltage: float = 21.2) -> HumanDecisionRequest:
    return _unimplemented_decision(_evidence(voltage))


def explicit_review(voltage: float = 21.2) -> HumanDecisionRequest:
    return human_judgment(_evidence(voltage), instructions=_INSTRUCTIONS)


def ordinary_unimplemented(voltage: float = 21.2) -> NoReturn:
    # 普通函数不使用判断组件协议，必须保留失败而不能自动转人工。
    raise NotImplementedError(
        '这是故意的普通函数失败示例，不应自动转人工。 / '
        'Intentional ordinary-function failure example; do not convert to human review.'
    )


def empty_decision(voltage: float = 21.2) -> None:
    # 故意保留空实现：None 不是是/否结果，也不能自动触发人工接管。
    pass


def record_result() -> None:
    """仅作为示例流程的记录步骤，不写文件或操作设备。"""
    return None
