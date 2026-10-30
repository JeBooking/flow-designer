import asyncio

from .charts import temperature_chart
from .models import Measurement
from .simulator import CoolingRig
__diagnosis_stateless__ = True


class CoolingSession:
    """一次排查持有一台设备；节点直接调用这些普通 Python 方法。"""

    def __init__(self, scenario: str = 'fan', device_id: str = 'COOL-01'):
        self.scenario = scenario
        self.device = CoolingRig(device_id, scenario)
        self.initial = self.device.read('initial')

    def __diagnosis_checkpoint__(self):
        return dict(self.__dict__)

    @classmethod
    def __diagnosis_restore__(cls, state):
        instance = object.__new__(cls)
        instance.__dict__.update(state)
        return instance

    def is_overheated(self) -> bool:
        """判断初始温度是否超过工程 CSV 文件中的阈值。"""
        return self.initial.temperature > self.device.limits.max_temperature

    def collect_air(self) -> Measurement:
        """风路采集返回原生 Measurement，不转换成平台参数。"""
        return self.device.read('air')

    def collect_fan(self) -> Measurement:
        """风机采集可以与风路采集并行进行。"""
        return self.device.read('fan')

    def filter_is_blocked(self, air_sample: Measurement) -> bool:
        """接收 air_sample 节点的原始对象，判断风量是否过低。"""
        self._check_sample(air_sample, 'air')
        return air_sample.airflow < self.device.limits.min_airflow

    def fan_is_faulty(self, fan_sample: Measurement) -> bool:
        """接收 fan_sample 节点的原始对象，判断转速是否过低。"""
        self._check_sample(fan_sample, 'fan')
        return fan_sample.fan_rpm < self.device.limits.min_fan_rpm

    def clean_filter(self) -> None:
        """模拟清理滤网；设备状态由设备实例自身维护。"""
        self.device.clean_filter()

    async def restart_fan(self) -> None:
        """模拟异步重启，卡死场景保留原始 Python 异常。"""
        await asyncio.sleep(0.02)
        self.device.restart_fan()

    def report_filter(self) -> dict:
        """清理后复采，并返回可在平台显示的温度图表。"""
        return self._report('filter')

    def report_fan(self) -> dict:
        """重启后复采，并确认设备已经降温。"""
        return self._report('fan')

    def report_healthy(self) -> dict:
        """记录无需处置的正常场景。"""
        return self._report('healthy')

    def summary(self) -> dict:
        """供单接口调试查看当前实例，不改变故障状态。"""
        reading = self.device.read('status')
        return {'scenario': self.scenario, 'device_id': reading.device_id,
                'temperature': reading.temperature, 'airflow': reading.airflow,
                'fan_rpm': reading.fan_rpm, 'repairs': list(self.device.repairs)}

    def _check_sample(self, sample, channel):
        if not isinstance(sample, Measurement):
            raise TypeError('Expected the original Measurement object, not its displayed text')
        if sample.device_id != self.device.device_id or sample.channel != channel:
            raise ValueError('Measurement belongs to a different device or channel')

    def _report(self, cause):
        reading = self.device.read('verification')
        if reading.temperature > self.device.limits.max_temperature:
            raise RuntimeError('Cooling verification failed: temperature remains above limit')
        return {'device_id': reading.device_id, 'scenario': self.scenario, 'cause': cause,
                'before': self.initial.temperature, 'after': reading.temperature,
                'repairs': list(self.device.repairs),
                'chartSvg': temperature_chart(reading.device_id, self.initial.temperature,
                                               reading.temperature, self.device.limits.max_temperature)}
