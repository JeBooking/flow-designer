"""决策层：只接受当前节点的连线 ID，不执行 BPMN 中的任意条件文本。"""


def decide(node, result, context):
    edges = node['outgoing']
    if not edges:
        raise RuntimeError('非终止节点没有后续连线 / Missing successor: ' + node['id'])
    if result is not None:
        for edge in edges:
            if edge['id'] == result:
                return edge['target']
        raise ValueError('诊断函数必须返回有效的连线 ID / Invalid outgoing flow ID: ' + repr(result))
    if len(edges) == 1 and not edges[0]['condition']:
        context.ask('确认诊断/步骤完成后按回车继续 / Press Enter to continue: ')
        return edges[0]['target']
    context.show('请选择下一步 / Select the next step:')
    for number, edge in enumerate(edges, 1):
        default = ' (默认/default)' if edge.get('default') else ''
        context.show(f"{number}. {edge['name'] or edge['id']} -> {edge['targetName']} [{edge['id']}] {edge['condition']}{default}")
    while True:
        answer = context.ask('序号或连线 ID / Number or flow ID: ').strip()
        for number, edge in enumerate(edges, 1):
            if answer in (str(number), edge['id']):
                return edge['target']
        context.show('无效选择 / Invalid choice')
