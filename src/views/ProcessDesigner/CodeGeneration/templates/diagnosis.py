"""诊断层：返回是/否结果；未实现时由判断组件请求人工决定。"""
from diagnostic_components import decision, HumanDecisionRequest


def diagnose(data, node, context):
    result = decision(instructions=node['assessment'])(HANDLERS[node['id']])(data, node, context)
    if isinstance(result, HumanDecisionRequest):
        context.show('人工诊断方法 / Manual diagnosis: ' + result.instructions)
        return None
    return result
