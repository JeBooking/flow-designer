"""示例外部项目：入口导出函数，内部实现仍按普通 Python 工程组织。"""
from .charts import summarize, draw_chart

__all__ = ['summarize', 'draw_chart']
