"""数据展示层：终端展示解析结果，可替换各节点函数为图表或其他界面。"""
import json
import webbrowser
from pathlib import Path


def default_display(data, node, context):
    context.show(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    if node.get('referenceImage'):
        resource = Path(__file__).resolve().parent / node['referenceImage']
        context.show('参考文件 / Reference file: ' + str(resource))
        context.show('浏览器不支持时，请使用本机兼容软件打开 / If unsupported in the browser, open with a compatible local application')
        if context.open_images:
            if not webbrowser.open(resource.as_uri()):
                context.show('请使用本机支持此格式的软件打开上述文件 / Open this file with a compatible local application')


def display(data, node, context):
    HANDLERS[node['id']](data, node, context)
