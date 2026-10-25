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
definition = json.loads((project / 'workflow.json').read_text(encoding='utf-8'))
assert definition['version'] == 4
assert (project / definition['nodes']['Inspect']['referenceImage']).read_bytes().startswith(b'\x89PNG')
assert not (project / 'source.bpmn').exists()
assert 'Inspect' in (project / 'IMPLEMENTATION.md').read_text(encoding='utf-8')
for filename in ('acquisition.py', 'parsing.py', 'display.py', 'diagnosis.py'):
    source = (project / filename).read_text(encoding='utf-8')
    assert '# 节点 ID: Inspect' in source, filename
    assert '# 输入:' in source and '# 输出:' in source and '# 调用关系:' in source, filename
    assert '对照额定电压判断' in source and '使用电压表' in source, filename

assert 'data:image/' not in (project / 'workflow.json').read_text(encoding='utf-8')
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
legacy = {'version': 2, 'start': 'Start', 'nodes': {
    'Start': {'id': 'Start', 'kind': 'start', 'outgoing': [{'target': 'Solved', 'condition': ''}]},
    'Solved': {'id': 'Solved', 'kind': 'problemSolved', 'outgoing': []}}}
assert execute([], workflow=legacy)[0]['history'] == ['Start', 'Solved']
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


# 串行失败消费当前思路；成功状态可落盘，恢复后不能重新领取兄弟分支。
import copy
serial = json.loads((project / 'workflow.json').read_text(encoding='utf-8'))
serial['mode'] = 'serial'
failed_node = copy.deepcopy(serial['nodes']['Inspect'])
failed_node.update(id='FailedIdea', name='', outgoing=[])
serial['nodes']['FailedIdea'] = failed_node
serial['nodes']['Inspect']['outgoing'].append({
    'id': 'Inspect_FailedIdea', 'target': 'FailedIdea', 'targetName': '',
    'branch': 'yes', 'condition': '', 'order': -10, 'default': False, 'name': '',
})
acquisition.HANDLERS['FailedIdea'] = lambda node, ctx: 26
importlib.import_module('parsing').HANDLERS['FailedIdea'] = lambda raw, node, ctx: raw
importlib.import_module('display').HANDLERS['FailedIdea'] = lambda data, node, ctx: None
diagnosis.HANDLERS['FailedIdea'] = lambda data, node, ctx: True
for name in ('Repair', 'SecondRepair'):
    actions.HANDLERS[name] = lambda node, ctx: ctx.data.setdefault('actions', []).append(node['id'])
paused, _, _ = execute([], workflow=serial)
assert paused['status'] == 'paused', paused
assert len(paused['diagnosticFailures']) == 1
assert paused['diagnosticFailures'][0]['path'] == ['Start', 'Inspect', 'FailedIdea']
assert paused['history'].index('FailedIdea') < paused['history'].index('Repair')
assert 'SecondRepair' not in paused['history']
state = json.loads(json.dumps(paused['state']))
assert execute([], workflow=serial, resume=state)[0]['status'] == 'paused'
continued = execute([], workflow=serial, resume=state, success_action='continue')[0]
assert continued['status'] == 'problemSolved', continued
assert continued['history'].count('Inspect') == 1
assert continued['history'].count('Repair') == 1
assert continued['history'].count('SecondRepair') == 1
finished = execute([], workflow=serial, resume=state, success_action='finish')[0]
assert finished['status'] == 'problemSolved' and 'SecondRepair' not in finished['history']
assert finished['diagnosticReviews'][0]['action'] == 'finish'
all_failed = copy.deepcopy(serial)
all_failed['nodes']['Inspect']['outgoing'] = [all_failed['nodes']['Inspect']['outgoing'][-1]]
assert execute([], workflow=all_failed)[0]['status'] == 'failed'
all_failed['mode'] = 'parallel'
assert execute([], workflow=all_failed)[0]['status'] == 'failed'
# 单个不匹配出口与零出口具有相同失败语义；无效 yes/no 值仍应拒绝。
all_failed['nodes']['FailedIdea']['outgoing'] = [
    dict(serial['nodes']['Inspect']['outgoing'][0], branch='no')]
assert execute([], workflow=all_failed)[0]['diagnosticFailures'][0]['node'] == 'FailedIdea'


def fail(node, context):
    raise OSError('device offline')


acquisition.HANDLERS['Inspect'] = fail
try:
    execute([])
    raise AssertionError('Operational errors must not trigger manual fallback')
except OSError:
    pass
print('Generated Python: concurrent groups, serial priority, failures, durable success pause/resume/finish, terminal merges, data, subflows and step limits verified.')
