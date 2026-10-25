"""无硬件副作用的依赖关系示例，参数从流程数据自动匹配。"""
def ready(scenario='normal'):
    return {'next': scenario != 'unavailable', 'voltage': 24, 'connected': True}

def power_ok(voltage):
    return voltage >= 22

def record_power():
    pass
