"""数据解析层：默认原样返回，在各节点函数内补充格式转换和校验。"""


def parse(raw, node, context):
    return HANDLERS[node['id']](raw, node, context)
