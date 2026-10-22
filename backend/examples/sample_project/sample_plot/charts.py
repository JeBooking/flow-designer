"""只用于验证接入链路，不约束实际项目的数据和绘图接口。"""
from pathlib import Path


def summarize(values):
    """返回一组数值的数量与平均值。"""
    return {'count': len(values), 'mean': sum(values) / len(values) if values else None}


def draw_chart(values, output='example-chart.svg'):
    """将数据画成简单 SVG，返回本机文件路径。"""
    points = ' '.join(f'{20 + index * 30},{180 - float(value)}'
                      for index, value in enumerate(values))
    target = Path(output).resolve()
    target.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="220">'
                      f'<polyline points="{points}" fill="none" stroke="blue"/></svg>', encoding='utf-8')
    return str(target)
