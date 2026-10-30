"""验证旧示例必须迁移分组标签，当前分组示例可直接编译。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from flowable_bridge import compile_workflow

examples = ROOT / 'src/views/ProcessDesigner/examples'
for path in sorted(examples.glob('*.bpmn')):
    xml = path.read_text(encoding='utf-8')
    if path.name == 'parallel-dependencies.bpmn':
        compile_workflow(xml)
    else:
        try:
            compile_workflow(xml)
        except ValueError as error:
            assert 'Select Yes/No for branch' in str(error), (path.name, str(error))
        else:
            raise AssertionError('Legacy example silently accepted: ' + path.name)
    print('PASS: explicit migration boundary / ' + path.name)
