"""动作层：只有明确完成自动动作或人工确认后才允许继续。"""


def execute(node, context):
    try:
        HANDLERS[node['id']](node, context)
    except NotImplementedError:
        context.show('执行动作 / Action: ' + (node['actionText'] or node['documentation'] or node['name']))
        answer = context.ask('完成动作后输入 yes，其他输入停止 / Type yes after completion: ')
        if answer.strip().lower() != 'yes':
            raise RuntimeError('动作未确认，流程停止 / Action not confirmed: ' + node['id'])
