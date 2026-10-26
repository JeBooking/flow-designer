from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    device_id: str
    channel: str
    sequence: int
    temperature: float
    airflow: float
    fan_rpm: int


@dataclass(frozen=True)
class Limits:
    max_temperature: float
    min_airflow: float
    min_fan_rpm: int
