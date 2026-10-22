"""流程调度：Python 3.10+ 标准库即可运行。"""
import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import acquisition
import parsing
import display
import diagnosis
import actions
import routing


@dataclass
class Context:
    ask: Callable[[str], str] = input
    show: Callable[[str], None] = print
    open_images: bool = True
    data: dict = field(default_factory=dict)
    history: list = field(default_factory=list)


def run(workflow=None, supplied=None, context=None, max_steps=1000):
    """supplied 为 {节点ID: 原始数据}，支持 null/空列表等合法输入。"""
    if workflow is None:
        workflow = json.loads(Path(__file__).with_name('workflow.json').read_text(encoding='utf-8'))
    supplied = {} if supplied is None else supplied
    if not isinstance(supplied, dict):
        raise ValueError('supplied must be a dictionary keyed by node ID')
    context = context or Context()
    nodes = workflow['nodes']
    current = workflow['start']
    parents = []
    for _ in range(max_steps):
        node = nodes[current]
        kind = node['kind']
        context.show('\n' + node['name'] + ' [' + current + ']')
        context.history.append(current)
        result = None
        if kind in ('problemSolved', 'escalation', 'jump'):
            context.show(node['documentation'] or node['name'])
            return {'status': kind, 'node': current, 'history': list(context.history)}
        if kind == 'subprocess':
            parents.append(current)
            current = node['start']
            continue
        if kind == 'end':
            if not parents:
                raise RuntimeError('顶层结束事件不是诊断结果 / End event is not a diagnostic outcome')
            node = nodes[parents.pop()]
        elif kind == 'investigation':
            raw = acquisition.fetch(node, context, supplied)
            parsed = parsing.parse(raw, node, context)
            display.display(parsed, node, context)
            result = diagnosis.diagnose(parsed, node, context)
            context.data[current] = {'raw': raw, 'parsed': parsed, 'result': result}
        elif kind in ('investigationAction', 'remediation', 'deepDiagnosis'):
            actions.execute(node, context)
        elif kind == 'conclusion':
            context.show(node['conclusionText'])
        # 无条件的开始、结论和已确认动作可以直接流转。
        edges = node['outgoing']
        if kind != 'investigation' and len(edges) == 1 and not edges[0]['condition']:
            current = edges[0]['target']
        else:
            current = routing.decide(node, result, context)
    raise RuntimeError('超过最大执行步数，检查循环 / Maximum steps exceeded')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Diagnostic workflow / 诊断链路')
    parser.add_argument('--data', help='JSON file: {node_id: raw_data}')
    parser.add_argument('--max-steps', type=int, default=1000)
    parser.add_argument('--no-images', action='store_true')
    args = parser.parse_args()
    try:
        supplied = json.loads(Path(args.data).read_text(encoding='utf-8-sig')) if args.data else {}
        print(json.dumps(run(supplied=supplied, context=Context(open_images=not args.no_images),
                             max_steps=args.max_steps), ensure_ascii=False, indent=2))
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, '操作取消 / Cancelled\n')
    except Exception as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
