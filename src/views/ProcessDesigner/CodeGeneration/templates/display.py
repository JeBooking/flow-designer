"""数据展示层：终端展示解析结果，可替换各节点函数为图表或其他界面。"""
import json
import webbrowser
from pathlib import Path


def default_display(data, node, context):
    context.show(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    if node.get('referenceImage'):
        image = Path(__file__).resolve().parent / node['referenceImage']
        context.show('参考图 / Reference image: ' + str(image))
        if context.open_images:
            webbrowser.open(image.as_uri())


def display(data, node, context):
    HANDLERS[node['id']](data, node, context)
