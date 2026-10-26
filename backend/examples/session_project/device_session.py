from dataclasses import dataclass
from typing import Optional


@dataclass
class Reading:
    device_id: str
    voltage: float
    attempt: int


class Device:
    """设备会话示例：采集对象与恢复状态直接保留在 Python 中。"""

    def __init__(self, device_id: str = 'M01', threshold: float = 24):
        self.device_id = device_id
        self.threshold = threshold
        self.recovered = False
        self.attempts = 0
        self.latest: Optional[Reading] = None

    def ready(self) -> bool:
        """入口排查确认已进入设备会话，再转入采集动作。"""
        return True

    def collect(self) -> Reading:
        """返回原生采集对象；后续判断直接接收该对象。"""
        self.attempts += 1
        self.latest = Reading(self.device_id, 24.5 if self.recovered else 22.6, self.attempts)
        return self.latest

    def is_low(self, reading: Reading) -> bool:
        """判断电压是否过低，不要求重复填写设备内部状态。"""
        return reading.voltage < self.threshold

    def restore(self) -> None:
        """模拟恢复动作；实际设备动作由业务工程实现。"""
        self.recovered = True

    async def verify(self) -> bool:
        """在同一设备实例复采，返回恢复是否成功。"""
        return not self.is_low(self.collect())

    async def restore_and_verify(self) -> None:
        """处置完成前复核，失败时让任务报错，避免错误标记问题解决。"""
        self.restore()
        if not await self.verify():
            raise RuntimeError('Device recovery verification failed')


def create_session(device_id: str = 'M01', threshold: float = 24) -> Device:
    """也可将此工厂名登记为入口，返回类型注解支持免实例化发现。"""
    return Device(device_id, threshold)
