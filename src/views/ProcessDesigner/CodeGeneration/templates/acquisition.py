"""数据获取层：自动函数未实现时，说明人工采集步骤并接受输入。"""
import json
from pathlib import Path


def fetch(node, context, supplied):
    if node['id'] in supplied:
        return supplied[node['id']]
    try:
        return HANDLERS[node['id']](node, context)
    except NotImplementedError:
        context.show('需要数据 / Required data: ' + node['observation'])
        context.show('人工获取方法 / Manual acquisition: ' + node['acquisition'])
        value = context.ask('输入数据（JSON 或文本），或 @JSON文件路径 / Data or @JSON file: ')
        if value.startswith('@'):
            return json.loads(Path(value[1:]).expanduser().read_text(encoding='utf-8-sig'))
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
