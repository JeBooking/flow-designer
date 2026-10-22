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


result, context, messages = execute(['{"voltage":24}', 'normal', 'yes', 'fixed'])
assert result['status'] == 'problemSolved'
assert context.data['Inspect']['parsed'] == {'voltage': 24}
assert any('使用电压表' in m for m in messages)
assert any('对照额定电压判断' in m for m in messages)
assert execute(['bad'], {'Inspect': None})[0]['status'] == 'escalation'
assert execute(['normal', 'yes', 'handoff'], {'Inspect': 24})[0]['status'] == 'jump'
assert execute(['retry', 'yes', 'normal', 'yes', 'fixed'], {'Inspect': 24})[0]['history'].count('Inspect') == 2
assert execute(['normal', 'yes', 'deeper', 'yes'], {'Inspect': 24})[0]['status'] == 'problemSolved'
data_file = root / 'data.json'
data_file.write_text('{"voltage": 25}', encoding='utf-8')
assert execute(['@' + str(data_file), 'bad'])[1].data['Inspect']['raw']['voltage'] == 25
nested = json.loads((root / 'nested.json').read_text(encoding='utf-8'))
assert execute([], workflow=nested)[0]['history'] == ['Start', 'Sub', 'InnerStart', 'InnerEnd', 'Solved']
acquisition.HANDLERS['Inspect'] = lambda node, ctx: 26
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: 'bad'
assert execute([])[0]['status'] == 'escalation'
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: 'nonexistent'
try:
    execute([])
    raise AssertionError('Invalid flow must fail')
except ValueError:
    pass
diagnosis.HANDLERS['Inspect'] = lambda data, node, ctx: 'retry'
actions.HANDLERS['Action'] = lambda node, ctx: None
try:
    execute([], max_steps=6)
    raise AssertionError('Loop limit must stop execution')
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
print('Generated Python: manual data, file data, injected data, automatic hooks, branching, actions, subflow, handoff, failure and loop limit verified.')
