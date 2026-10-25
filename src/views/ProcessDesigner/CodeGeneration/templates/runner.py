"""流程调度：Python 3.10+ 标准库即可运行。"""
import argparse
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


def run(workflow=None, supplied=None, context=None, max_steps=1000, resume=None, success_action=None):
    """串行成功后返回可保存的 state，调用方显式选择 continue/finish 后恢复。"""
    if workflow is None:
        workflow = json.loads(Path(__file__).with_name('workflow.json').read_text(encoding='utf-8'))
    supplied = {} if supplied is None else supplied
    if not isinstance(supplied, dict):
        raise ValueError('supplied must be a dictionary keyed by node ID')
    context = context or Context()
    nodes = workflow['nodes']
    mode = workflow.get('mode', 'parallel')
    if mode not in ('parallel', 'serial'):
        raise ValueError('Invalid diagnosis mode / 无效排查模式')
    signature = hashlib.sha256(json.dumps(workflow, sort_keys=True).encode()).hexdigest()
    if resume and (mode != 'serial' or resume.get('workflow') != signature):
        raise ValueError('Resume state belongs to another workflow / 恢复状态与流程不匹配')
    if success_action not in (None, 'continue', 'finish'):
        raise ValueError('Choose continue or finish / 请选择继续或结束排查')
    lock, prompt_lock = threading.Lock(), threading.Lock()
    steps = [resume.get('steps', 0) if resume else 0]
    failures = list(resume.get('diagnosticFailures', [])) if resume else []
    outcomes = list(resume.get('outcomes', [])) if resume else []
    reviews = list(resume.get('diagnosticReviews', [])) if resume else []
    queue = list(resume['queue']) if resume else [{'node': workflow['start'], 'parents': [], 'path': []}]
    if resume:
        context.data.update(resume.get('data', {}))
        context.history[:] = resume.get('history', [])
    original_ask = context.ask
    def ask(prompt):
        with prompt_lock:
            return original_ask(prompt)
    context.ask = ask
    def execute(current, parents, path):
        with lock:
            steps[0] += 1
            if steps[0] > max_steps:
                raise RuntimeError('超过最大执行步数 / Maximum steps exceeded')
        node = nodes[current]
        kind = node['kind']
        name = node.get('name') or current
        path = path + [current]
        context.show('\n' + name + ' [' + current + ']')
        context.history.append(current)
        result = None
        if kind in ('problemSolved', 'escalation', 'jump'):
            context.show(node.get('detailText') or node.get('documentation') or name)
            return [], {'status': kind, 'node': current, 'path': path}
        if kind == 'subprocess':
            return [{'node': node['start'], 'parents': parents + [current], 'path': path}], None
        if kind == 'end':
            if not parents:
                raise RuntimeError('顶层结束事件不是诊断结果 / End event is not a diagnostic outcome')
            node = nodes[parents[-1]]
            parents = parents[:-1]
        elif kind == 'investigation':
            raw = acquisition.fetch(node, context, supplied)
            parsed = parsing.parse(raw, node, context)
            display.display(parsed, node, context)
            result = diagnosis.diagnose(parsed, node, context)
            context.data[current] = {'raw': raw, 'parsed': parsed, 'result': result}
        elif kind in ('investigationAction', 'remediation', 'deepDiagnosis'):
            actions.execute(node, context)
        elif kind == 'conclusion':
            context.show(node.get('detailText') or node.get('conclusionText', ''))
        edges = node['outgoing']
        if mode == 'serial':
            node = dict(node, outgoing=sorted(edges, key=lambda edge: edge.get('order', 0)))
            edges = node['outgoing']
        if kind != 'investigation' and len(edges) == 1 and not edges[0]['condition']:
            targets = [edges[0]['target']]
        else:
            targets = routing.decide(node, result, context)
        if not targets:
            record = {'node': current, 'nodeId': current, 'result': result,
                      'reason': 'No matching outgoing branch / 判断结果没有匹配出口',
                      'path': path, 'time': datetime.now(timezone.utc).isoformat()}
            with lock:
                failures.append(record)
            return [], {'status': 'failed', 'node': current, 'path': path}
        return [{'node': target, 'parents': list(parents), 'path': path} for target in targets], None
    def walk(job):
        while True:
            targets, outcome = execute(job['node'], job['parents'], job['path'])
            if outcome:
                return [outcome]
            if len(targets) != 1:
                break
            job = targets[0]
        # 各条依赖只调度一次；某个思路失败不会重新触发同组任务。
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures = [pool.submit(walk, target) for target in targets]
            return [outcome for future in futures for outcome in future.result()]
    def report(paused=False):
        status = 'paused' if paused else next((kind for kind in ('problemSolved', 'escalation', 'jump')
            if any(item['status'] == kind for item in outcomes)), 'failed')
        selected = outcomes[-1] if paused else next((item for item in outcomes if item['status'] == status), outcomes[-1] if outcomes else {})
        result = {'status': status, 'diagnosticStatus': status, 'node': selected.get('node'),
                  'outcomes': list(outcomes), 'history': list(context.history),
                  'diagnosticFailures': list(failures), 'diagnosticReviews': list(reviews)}
        if paused:
            result['state'] = {'workflow': signature, 'queue': list(queue), 'steps': steps[0],
                'outcomes': list(outcomes), 'history': list(context.history), 'data': dict(context.data),
                'diagnosticFailures': list(failures), 'diagnosticReviews': list(reviews)}
        return result
    try:
        if mode == 'parallel':
            if resume:
                raise ValueError('Parallel runs cannot resume serial queues')
            outcomes.extend(walk(queue[0]))
            return report()
        if resume:
            if success_action is None:
                return report(paused=True)
            reviews.append({'action': success_action, 'time': datetime.now(timezone.utc).isoformat(),
                            'remainingQueue': list(queue)})
            if success_action == 'finish':
                queue.clear()
                return report()
        while queue:
            job = queue.pop(0)
            targets, outcome = execute(job['node'], job['parents'], job['path'])
            queue[0:0] = targets
            if outcome:
                outcomes.append(outcome)
                if outcome['status'] == 'problemSolved' and queue:
                    return report(paused=True)
        return report()
    finally:
        context.ask = original_ask


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Diagnostic workflow / 诊断链路')
    parser.add_argument('--data', help='JSON file: {node_id: raw_data}')
    parser.add_argument('--max-steps', type=int, default=1000)
    parser.add_argument('--no-images', action='store_true')
    parser.add_argument('--resume', help='JSON file containing a returned state')
    parser.add_argument('--success-action', choices=('continue', 'finish'))
    args = parser.parse_args()
    try:
        supplied = json.loads(Path(args.data).read_text(encoding='utf-8-sig')) if args.data else {}
        state = json.loads(Path(args.resume).read_text(encoding='utf-8-sig')) if args.resume else None
        print(json.dumps(run(supplied=supplied, context=Context(open_images=not args.no_images),
            max_steps=args.max_steps, resume=state, success_action=args.success_action), ensure_ascii=False, indent=2))
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, '操作取消 / Cancelled\n')
    except Exception as error:
        parser.exit(1, f'{type(error).__name__}: {error}\n')
