"""登记时独立导入工程发现接口；实际调试和流程由会话进程运行。"""
import contextlib
import importlib
import io
import json
from pathlib import Path
import sys
import traceback
from python_runtime import NativeRuntime, display_value, member, public_members


def execute(request):
    project = Path(request['path']).resolve()
    sys.path[:0] = [str(project / 'src'), str(project), str(project.parent)]
    module = importlib.import_module(request['module'])
    location = getattr(module, '__file__', None)
    if not location or project not in Path(location).resolve().parents:
        raise ValueError('Entry module must come from the selected project directory')
    runtime = NativeRuntime()
    try:
        if request['operation'] == 'discover':
            return runtime.discover(request['module'], request.get('factory', ''), request.get('inputs', {}))
        owner = runtime.target(request['module'], request.get('factory', ''), request.get('inputs', {}))
        if not request.get('factory') and request['function'] not in public_members(owner):
            raise ValueError('Function is not public in this entry module')
        function = member(owner, request['function'])
        args, kwargs = request.get('args', []), request.get('kwargs', {})
        if not isinstance(args, list) or not isinstance(kwargs, dict):
            raise TypeError('args must be an array and kwargs must be an object')
        value = runtime.wait(function(*args, **kwargs))
        payload = display_value(value)
        return {'result': payload, 'representation': 'json' if payload is value else 'repr'}
    finally:
        runtime.close()


if __name__ == '__main__':
    output, errors = io.StringIO(), io.StringIO()
    try:
        request = json.loads(sys.stdin.read())
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            response = {'ok': True, **execute(request)}
    except BaseException as error:
        response = {'ok': False, 'error': f'{type(error).__name__}: {error}',
                    'traceback': traceback.format_exc()}
    response.update(stdout=output.getvalue(), stderr=errors.getvalue())
    # 独立结果文件避免外部原生库直接写 stdout 时污染通信协议。
    Path(sys.argv[1]).write_text(json.dumps(response, ensure_ascii=False), encoding='utf-8')
