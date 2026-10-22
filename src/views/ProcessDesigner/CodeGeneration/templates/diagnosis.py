"""诊断层：返回下一条连线的 ID；None 表示需要人工决定。"""


def diagnose(data, node, context):
    try:
        return HANDLERS[node['id']](data, node, context)
    except NotImplementedError:
        context.show('人工诊断方法 / Manual diagnosis: ' + node['assessment'])
        return None
