"""每个流程、每个工程一个进程，保留模块缓存、实例和异步事件循环。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import traceback

from diagnostic_components import HumanDecisionRequest
from python_runtime import NativeRuntime, decision_branch, display_value, member, public_members


def main():
    project = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    root = Path(project['path']).resolve()
    sys.path[:0] = [str(root / 'src'), str(root), str(root.parent)]
    runtime = NativeRuntime()

    def respond(request_file):
        source = Path(request_file)
        request = json.loads(source.read_text(encoding='utf-8'))
        try:
            if request.get('operation') == 'debug':
                owner = runtime.target(project['module'], project.get('factory', ''), request.get('inputs', {}))
                if not project.get('factory') and request['function'] not in public_members(owner):
                    raise ValueError('Function is not public in this entry module')
                function = member(owner, request['function'])
                args, kwargs = request.get('args', []), request.get('kwargs', {})
                if not isinstance(args, list) or not isinstance(kwargs, dict):
                    raise TypeError('args must be an array and kwargs must be an object')
                value = runtime.wait(function(*args, **kwargs))
                payload = display_value(value)
                response = {'ok': True, 'result': payload,
                            'representation': 'json' if payload is value else 'repr'}
            else:
                binding = request['binding']
                result = runtime.execute(binding, request['variables'])
                requested = isinstance(result, HumanDecisionRequest)
                manual = requested or bool(binding.get('humanDecision'))
                response = {'ok': True, 'result': display_value(result.data if requested else result),
                            'human': manual, 'request': {'instructions': result.instructions} if requested else {}}
                if not manual and (binding.get('kind') == 'investigation' or binding.get('branches')):
                    response['route'] = decision_branch(result, binding)
                elif not manual and not binding.get('kind') and len(binding.get('outgoing', [])) > 1:
                    response['route'] = result['next']
        except BaseException as error:
            response = {'ok': False, 'error': f'{type(error).__name__}: {error}',
                        'traceback': traceback.format_exc()}
        destination = source.with_suffix('.result')
        temporary = source.with_suffix('.tmp')
        temporary.write_text(json.dumps(response, ensure_ascii=False), encoding='utf-8')
        temporary.replace(destination)

    # 业务输出走进程日志文件，原生库直写 stdout 也不会破坏通信；并行节点可并发调用同一实例。
    try:
        with ThreadPoolExecutor(max_workers=32) as pool:
            for line in sys.stdin:
                pool.submit(respond, line.strip())
    finally:
        runtime.close()


if __name__ == '__main__':
    main()
