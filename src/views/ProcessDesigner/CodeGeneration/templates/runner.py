"""流程调度：Python 3.10+ 标准库即可运行。"""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor
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
    lock = threading.Lock()
    prompt_lock = threading.Lock()
    steps = [0]
    original_ask = context.ask
    def ask(prompt):
        with prompt_lock:
            return original_ask(prompt)
    context.ask = ask
    def walk(current, parents):
        while True:
            with lock:
                steps[0] += 1
                if steps[0] > max_steps:
                    raise RuntimeError('超过最大执行步数 / Maximum steps exceeded')
            node = nodes[current]
            kind = node['kind']
            context.show('\n' + node['name'] + ' [' + current + ']')
            context.history.append(current)
            result = None
            if kind in ('problemSolved', 'escalation', 'jump'):
                context.show(node['documentation'] or node['name'])
                return [{'status': kind, 'node': current}]
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
                targets = [edges[0]['target']]
            else:
                targets = routing.decide(node, result, context)
            if len(targets) > 1:
                # 同组任务并发启动，不使用完成先后或连线顺序决定依赖。
                with ThreadPoolExecutor(max_workers=len(targets)) as pool:
                    futures = [pool.submit(walk, target, list(parents)) for target in targets]
                    return [outcome for future in futures for outcome in future.result()]
            current = targets[0]
    try:
        outcomes = walk(workflow['start'], [])
        status = next((kind for kind in ('escalation', 'jump', 'problemSolved')
                       if any(item['status'] == kind for item in outcomes)), 'completed')
        return {'status': status, 'node': next(item['node'] for item in outcomes if item['status'] == status), 'outcomes': outcomes,
                'history': list(context.history)}
    finally:
        context.ask = original_ask


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
