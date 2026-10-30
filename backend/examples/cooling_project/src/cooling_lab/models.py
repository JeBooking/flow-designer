from dataclasses import dataclass
__diagnosis_stateless__ = True


@dataclass(frozen=True)
class Measurement:
    device_id: str
    channel: str
    sequence: int
    temperature: float
    airflow: float
    fan_rpm: int

    def __diagnosis_checkpoint__(self):
        return dict(self.__dict__)

    @classmethod
    def __diagnosis_restore__(cls, state):
        return cls(**state)


@dataclass(frozen=True)
class Limits:
    max_temperature: float
    min_airflow: float
    min_fan_rpm: int

    def __diagnosis_checkpoint__(self):
        return dict(self.__dict__)

    @classmethod
    def __diagnosis_restore__(cls, state):
        return cls(**state)
