"""每次操作在独立 Python 进程内导入项目，避免同名包和模块缓存串用。"""
import asyncio
import contextlib
import importlib
import inspect
import io
import json
from pathlib import Path
import sys
import traceback


def public_functions(module):
    names = getattr(module, '__all__', None)
    if names is None:
        names = [name for name, value in vars(module).items()
                 if not name.startswith('_') and inspect.isroutine(value)
                 and getattr(value, '__module__', None) == module.__name__]
    return {name: getattr(module, name) for name in names
            if isinstance(name, str) and inspect.isroutine(getattr(module, name, None))}


def execute(request):
    project = Path(request['path']).resolve()
    sys.path[:0] = [str(project / 'src'), str(project), str(project.parent)]
    module = importlib.import_module(request['module'])
    location = getattr(module, '__file__', None)
    if not location or project not in Path(location).resolve().parents:
        raise ValueError('Entry module must come from the selected project directory')
    functions = public_functions(module)
    if request['operation'] == 'discover':
        result = []
        for name, function in functions.items():
            try:
                signature = str(inspect.signature(function))
            except (ValueError, TypeError):
                signature = '(...)'
            result.append({'name': name, 'signature': signature,
                           'description': inspect.getdoc(function) or ''})
        return {'interfaces': result, 'moduleFile': str(location)}
    function = functions.get(request['function'])
    if function is None:
        raise ValueError('Function is not public in this entry module')
    args, kwargs = request.get('args', []), request.get('kwargs', {})
    if not isinstance(args, list) or not isinstance(kwargs, dict):
        raise ValueError('args must be an array and kwargs must be an object')
    value = function(*args, **kwargs)
    if inspect.isawaitable(value):
        value = asyncio.run(value)
    try:
        json.dumps(value, allow_nan=False)
        return {'result': value, 'representation': 'json'}
    except (TypeError, ValueError):
        return {'result': repr(value), 'representation': 'repr'}


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
