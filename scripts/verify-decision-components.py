"""组件独立于引擎验证：同步/异步、基类/装饰器、业务异常与适配边界。"""
import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
from diagnostic_components import DecisionComponent, HumanDecisionRequest, decision
from flowable_worker import execute

data = {'samples': [21, 22]}
request = DecisionComponent().run(data, instructions='Check samples', options=['yes', 'no'])
assert isinstance(request, HumanDecisionRequest) and request.data is data
assert request.instructions == 'Check samples' and request.options == ('yes', 'no')

class Automatic(DecisionComponent):
    def decide(self, data):
        return {'next': 'yes', 'value': min(data['samples'])}

assert Automatic().run(data)['next'] == 'yes'

@decision(instructions='Manual check')
def pending(data):
    raise NotImplementedError()

@decision()
async def async_pending(data):
    raise NotImplementedError()

@decision()
async def async_ready(data):
    return data

assert pending(data=data).data is data
assert asyncio.run(async_pending(data)).data is data
assert asyncio.run(async_ready(data)) is data

@decision()
def broken(data):
    raise ValueError('Business failure')

try:
    broken(data)
except ValueError:
    pass
else:
    raise AssertionError('Business failure incorrectly became human judgment')

binding = {'module': '__main__', 'function': 'pending', 'kwargs': {'data': data},
           'outgoing': ['yes', 'no'], 'humanDecision': False}
assert isinstance(execute(binding, {}), HumanDecisionRequest)

def undecorated(data):
    raise NotImplementedError()

try:
    execute(dict(binding, function='undecorated'), {})
except NotImplementedError:
    pass
else:
    raise AssertionError('Worker must not decide whether business code is implemented')
print('PASS: reusable base/decorator, sync/async fallback, automatic results and error boundaries')
