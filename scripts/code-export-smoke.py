"""验证实际导出工程，不依赖第三方 Python 包。"""
import compileall
import importlib
import json
from pathlib import Path
import sys
import zipfile

root = Path(sys.argv[1])
with zipfile.ZipFile(root / 'project.zip') as archive:
    assert archive.testzip() is None
    archive.extractall(root / 'project')
project = root / 'project'
assert compileall.compile_dir(str(project), quiet=1)
assert (project / 'images/reference_1.png').read_bytes().startswith(b'\x89PNG')
sys.path.insert(0, str(project))
runner = importlib.import_module('runner')
acquisition = importlib.import_module('acquisition')
diagnosis = importlib.import_module('diagnosis')
actions = importlib.import_module('actions')


def execute(answers, supplied=None, **kwargs):
    values = iter(answers)
    messages = []
    context = runner.Context(ask=lambda _: next(values), show=messages.append, open_images=False)
    result = runner.run(supplied=supplied, context=context, **kwargs)
    return result, context, messages



# 两个动作互相等待对方到达，只有真正并发才能通过。
import threading
barrier = threading.Barrier(2, timeout=3)
for name in ('Repair', 'SecondRepair'):
    actions.HANDLERS[name] = lambda node, ctx: barrier.wait()
result, context, messages = execute(['{"voltage":24}', 'yes'])
assert result['status'] == 'problemSolved'
assert len(result['outcomes']) == 2
assert {'Repair', 'SecondRepair'} <= set(result['history'])
assert context.data['Inspect']['parsed'] == {'voltage': 24}
assert any('使用电压表' in m for m in messages)
assert any('对照额定电压判断' in m for m in messages)
negative = execute(['no'], {'Inspect': None})[0]
assert {item['status'] for item in negative['outcomes']} == {'escalation', 'jump'}
assert not {'Repair', 'SecondRepair'} & set(negative['history'])
data_file = root / 'data.json'
data_file.write_text('{"voltage": 25}', encoding='utf-8')
assert execute(['@' + str(data_file), 'no'])[1].data['Inspect']['raw']['voltage'] == 25
nested = json.loads((root / 'nested.json').read_text(encoding='utf-8'))
assert execute([], workflow=nested)[0]['history'] == ['Start', 'Sub', 'InnerStart', 'InnerEnd', 'Solved']
acquisition.HANDLERS['Inspect'] = lambda node, ctx: 26
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: False
assert execute([])[0]['status'] == 'escalation'
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: 'nonexistent'
try:
    execute([])
    raise AssertionError('Invalid result must fail')
except ValueError:
    pass
# 全局步数限制覆盖所有并行路径。
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: True
try:
    execute([], max_steps=2)
    raise AssertionError('Step limit must stop execution')
except RuntimeError as error:
    assert 'Maximum steps' in str(error)


def fail(node, context):
    raise OSError('device offline')


acquisition.HANDLERS['Inspect'] = fail
try:
    execute([])
    raise AssertionError('Operational errors must not trigger manual fallback')
except OSError:
    pass
print('Generated Python: concurrent Yes/No groups, terminal merges, manual/automatic decisions, data, subflows, failure and step limits verified.')
