"""检查 worker 对异步接口和字面量参数的兼容性，不依赖 Java 服务。"""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_worker import execute, resolve

with tempfile.TemporaryDirectory(prefix='python-binding-') as temporary:
    Path(temporary, 'binding_example.py').write_text('''
async def inspect(value):
    return {"value": value, "next": "ready"}

def invalid():
    return {"next": "unknown"}
''', encoding='utf-8')
    sys.path.insert(0, temporary)
    try:
        result = execute({'module': 'binding_example', 'function': 'inspect',
            'kwargs': {'value': '$$device'}, 'outgoing': ['ready', 'retry']}, {})
        assert result == {'value': '$device', 'next': 'ready'}
        assert resolve({'items': ['$Inspect.data.0', '$$literal']}, {'Inspect': {'data': [24]}}) == {'items': [24, '$literal']}
        try:
            execute({'module': 'binding_example', 'function': 'invalid', 'kwargs': {},
                     'outgoing': ['ready', 'retry']}, {})
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid branch result accepted')
    finally:
        sys.path.remove(temporary)
print('PASS: async invocation, literal-dollar/nested arguments, invalid branch rejection')
