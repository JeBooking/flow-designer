"""判断组件示例：同一接口补齐业务代码后，无须修改流程图即可自动执行。"""
from diagnostic_components import DecisionComponent, decision


def review_voltage(reading):
    return DecisionComponent().run(reading,
        instructions='检查电压曲线与最低值，确认是否需要处置。 / Check the voltage curve and minimum before proceeding.')


@decision(instructions='确认恢复结果，选择问题解决或上升。 / Check recovery and choose solved or escalation.')
def review_recovery(data):
    raise NotImplementedError('Recovery decision is awaiting business implementation')
