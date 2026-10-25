"""决策层：只接受当前节点的连线 ID，不执行 BPMN 中的任意条件文本。"""


def decide(node, result, context):
    edges = node['outgoing']
    if not edges:
        raise RuntimeError('非终止节点没有后续连线 / Missing successor: ' + node['id'])
    if node['kind'] == 'investigation':
        value = result.get('next', result.get('result')) if isinstance(result, dict) else result
        if value is None:
            while True:
                value = context.ask('判断结果：是/否 / Result (yes/no): ').strip().lower()
                if value in ('yes', 'no', '是', '否'):
                    break
                context.show('请选择是或否 / Select yes or no')
        if value is True or value in ('yes', '是'):
            branch = 'yes'
        elif value is False or value in ('no', '否'):
            branch = 'no'
        else:
            branch = next((edge.get('branch') for edge in edges if edge['id'] == value), None)
        matches = {edge['target'] for edge in edges if edge.get('branch') == branch}
        if not branch or not matches:
            raise ValueError('Invalid Yes/No result / 无效的是或否结果: ' + repr(value))
        return list(matches)
    if node['kind'] != 'gateway':
        return list({edge['target'] for edge in edges})
    if result is not None:
        for edge in edges:
            if edge['id'] == result:
                return [edge['target']]
        raise ValueError('诊断函数必须返回有效的连线 ID / Invalid outgoing flow ID: ' + repr(result))
    if len(edges) == 1 and not edges[0]['condition']:
        context.ask('确认诊断/步骤完成后按回车继续 / Press Enter to continue: ')
        return [edges[0]['target']]
    context.show('请选择下一步 / Select the next step:')
    for number, edge in enumerate(edges, 1):
        default = ' (默认/default)' if edge.get('default') else ''
        context.show(f"{number}. {edge['name'] or edge['id']} -> {edge['targetName']} [{edge['id']}] {edge['condition']}{default}")
    while True:
        answer = context.ask('序号或连线 ID / Number or flow ID: ').strip()
        for number, edge in enumerate(edges, 1):
            if answer in (str(number), edge['id']):
                return [edge['target']]
        context.show('无效选择 / Invalid choice')
