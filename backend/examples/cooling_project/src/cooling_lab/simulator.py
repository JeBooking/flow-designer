import csv
import json
from pathlib import Path
import threading

from .models import Limits, Measurement


PROJECT = Path(__file__).resolve().parents[2]
__diagnosis_stateless__ = True


class CoolingRig:
    """模拟设备提供正常的业务对象，不依赖流程平台或 Flowable。"""

    def __init__(self, device_id, scenario):
        with (PROJECT / 'assets' / 'limits.csv').open(encoding='utf-8-sig', newline='') as file:
            values = {row['name']: float(row['value']) for row in csv.DictReader(file)}
        self.limits = Limits(values['max_temperature'], values['min_airflow'], int(values['min_fan_rpm']))
        profiles = json.loads((PROJECT / 'assets' / 'scenarios.json').read_text(encoding='utf-8-sig'))
        if scenario not in profiles:
            raise ValueError('Unknown cooling scenario: ' + scenario)
        self.device_id = device_id
        self.profile = profiles[scenario]
        self.filter_blocked = self.profile['filter_blocked']
        self.fan_fault = self.profile['fan_fault']
        self.unknown_heat = self.profile['unknown_heat']
        self.repairs = []
        self.sequence = 0
        self.lock = threading.RLock()

    def __diagnosis_checkpoint__(self):
        # 锁只是进程内同步手段；业务状态需保存，锁在恢复时重新创建。
        return {name: value for name, value in self.__dict__.items() if name != 'lock'}

    @classmethod
    def __diagnosis_restore__(cls, state):
        instance = object.__new__(cls)
        instance.__dict__.update(state)
        instance.lock = threading.RLock()
        return instance

    def read(self, channel):
        # 并行分支可以同时采集，快照与序号必须来自同一次受保护的状态读取。
        with self.lock:
            self.sequence += 1
            return Measurement(self.device_id, channel, self.sequence,
                               85.0 if self.filter_blocked or self.fan_fault or self.unknown_heat else 42.0,
                               0.18 if self.filter_blocked else 1.0,
                               300 if self.fan_fault else 1800)

    def clean_filter(self):
        with self.lock:
            if self.filter_blocked:
                self.filter_blocked = False
                self.repairs.append('clean_filter')

    def restart_fan(self):
        with self.lock:
            if self.profile['restart_fails']:
                raise RuntimeError('Fan restart failed: simulated seized motor on ' + self.device_id)
            if self.fan_fault:
                self.fan_fault = False
                self.repairs.append('restart_fan')
