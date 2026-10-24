"""独立的判断组件协议，不依赖 Flowable、浏览器或任何执行平台。"""
from dataclasses import dataclass
from functools import wraps
import inspect
from typing import Any


@dataclass(frozen=True)
class HumanDecisionRequest:
    data: Any
    instructions: str = ''
    options: tuple = ()


def human_judgment(data, instructions='', options=()):
    """请求人工判断；由宿主负责展示与收集结果，不阻塞业务线程。"""
    return HumanDecisionRequest(data, instructions, tuple(options))


def _run(judge, manual):
    try:
        result = judge()
    except NotImplementedError:
        return manual()
    if inspect.isawaitable(result):
        async def finish():
            try:
                return await result
            except NotImplementedError:
                return manual()
        return finish()
    return result


class DecisionComponent:
    """业务类只覆盖 decide；未覆盖或明确抛出 NotImplementedError 时转人工。"""
    def run(self, data, *, instructions='', options=()):
        return _run(lambda: self.decide(data),
                    lambda: human_judgment(data, instructions, options))

    def decide(self, data):
        raise NotImplementedError('Implement the business decision')


def decision(*, instructions='', options=()):
    """装饰已有判断函数；第一个参数（或 data 关键字参数）作为人工判断依据。"""
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            data = args[0] if args else kwargs.get('data')
            return _run(lambda: function(*args, **kwargs),
                        lambda: human_judgment(data, instructions, options))
        return wrapped
    return decorate
