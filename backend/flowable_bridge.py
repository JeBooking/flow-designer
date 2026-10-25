"""诊断图编译与官方 Flowable REST 的薄代理；流程调度由 Java 引擎完成。"""
import base64
import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid
import xml.etree.ElementTree as ET

BPMN = 'http://www.omg.org/spec/BPMN/20100524/MODEL'
FLOWABLE = 'http://flowable.org/bpmn'
DI = 'http://www.omg.org/spec/BPMN/20100524/DI'
for prefix, uri in [('bpmn', BPMN), ('flowable', FLOWABLE), ('bpmndi', DI),
                    ('dc', 'http://www.omg.org/spec/DD/20100524/DC'),
                    ('di', 'http://www.omg.org/spec/DD/20100524/DI')]:
    ET.register_namespace(prefix, uri)

def b(name):
    return '{' + BPMN + '}' + name

def f(name):
    return '{' + FLOWABLE + '}' + name

KINDS = {'investigation', 'investigationAction', 'conclusion', 'remediation',
         'deepDiagnosis', 'jump', 'problemSolved', 'escalation'}


def compile_workflow(xml):
    if not isinstance(xml, str) or '<!DOCTYPE' in xml.upper():
        raise ValueError('Invalid XML / 无效 XML')
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise ValueError('Malformed XML / XML 格式错误: ' + str(error)) from error
    processes = root.findall(b('process'))
    if len(processes) != 1:
        raise ValueError('Exactly one process is supported / 仅支持一个流程')
    process = processes[0]
    process_id = process.get('id')
    if not process_id:
        raise ValueError('Missing process ID / 缺少流程 ID')
    # 工作主题取决于执行定义，移动节点、翻译文字或 XML 重排不应使已启动的 worker 失效。
    signature = {'formatVersion': 5, 'processId': process_id, 'nodes': [], 'flows': []}
    executable_elements = [e for e in process if e.tag in (b('task'), b('startEvent'), b('sequenceFlow'))]
    execution_ids = [e.get('id') for e in executable_elements]
    if any(not value for value in execution_ids) or len(set(execution_ids)) != len(execution_ids):
        raise ValueError('Missing or duplicate element ID / 元素 ID 缺失或重复')
    for element in executable_elements:
        if element.get('default') or element.find(b('conditionExpression')) is not None:
            raise ValueError('Use the Python next result instead of flow conditions / 请使用 Python 的 next 返回值选择分支，并移除条件表达式和默认分支: ' + element.get('id'))
        if element.tag == b('sequenceFlow'):
            signature['flows'].append([element.get('id'), element.get('sourceRef'), element.get('targetRef'), element.get(f('diagnosisBranch'))])
        else:
            kwargs = json.loads(element.get(f('pythonArguments')) or '{}')
            if not isinstance(kwargs, dict):
                raise ValueError('Arguments must be an object / 参数必须是 JSON 对象')
            signature['nodes'].append({'id': element.get('id'), 'kind': element.get(f('diagnosisKind')),
                'module': element.get(f('pythonModule'), '').strip(),
                'function': element.get(f('pythonFunction'), '').strip(), 'kwargs': kwargs,
                'topic': element.get(f('pythonTopic'), '').strip(),
                'humanDecision': element.get(f('humanDecision')) == 'true'})
    signature['nodes'].sort(key=lambda item: item['id'])
    signature['flows'].sort()
    version = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()[:12]
    manifest = {'processId': process_id, 'version': version, 'bindings': {}, 'reviews': {}}
    starts = process.findall(b('startEvent'))
    if len(starts) != 1 or any(child.tag not in (b('outgoing'), b('documentation')) for child in starts[0]):
        raise ValueError('One plain start event is required / 需要一个普通开始事件')
    ids = {e.get('id') for e in root.iter() if e.get('id')}
    def new_id(stem):
        candidate = stem
        while candidate in ids:
            candidate += '_'
        ids.add(candidate)
        return candidate
    flows = process.findall(b('sequenceFlow'))
    nodes = {e.get('id'): e for e in process if e.tag in (b('task'), b('startEvent'))}
    if len(nodes) != len([e for e in process if e.tag in (b('task'), b('startEvent'))]):
        raise ValueError('Duplicate node IDs / 节点 ID 重复')
    for element in process:
        if element.tag not in (b('task'), b('startEvent'), b('sequenceFlow'),
                               b('documentation'), b('extensionElements')):
            raise ValueError('Unsupported executable element / 暂不支持执行: ' + element.tag)
    for edge in flows:
        if edge.get('sourceRef') not in nodes or edge.get('targetRef') not in nodes:
            raise ValueError('Invalid connection / 连线引用无效: ' + str(edge.get('id')))
        source, target = nodes[edge.get('sourceRef')], nodes[edge.get('targetRef')]
        source_kind, target_kind = source.get(f('diagnosisKind')), target.get(f('diagnosisKind'))
        allowed = {'investigation': {'investigation', 'investigationAction', 'conclusion', 'jump', 'escalation'},
            'investigationAction': {'investigation'}, 'conclusion': {'remediation', 'jump', 'escalation'},
            'remediation': {'remediation', 'jump', 'problemSolved', 'deepDiagnosis', 'escalation'},
            'jump': {'remediation', 'jump', 'problemSolved', 'deepDiagnosis', 'escalation'}}
        invalid = source is target or (source.tag == b('startEvent') and target_kind != 'investigation')
        invalid |= source_kind in allowed and target_kind not in allowed[source_kind]
        invalid |= target_kind == 'investigation' and source_kind not in ('investigation', 'investigationAction') and source.tag != b('startEvent')
        invalid |= target_kind in ('conclusion', 'investigationAction') and source_kind != 'investigation'
        if invalid:
            raise ValueError('Diagnostic connection violates rules / 诊断连接违反规则: ' + str(edge.get('id')))
    reached, pending = set(), [starts[0].get('id')]
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(e.get('targetRef') for e in flows if e.get('sourceRef') == current)
    if reached != set(nodes):
        raise ValueError('Disconnected nodes / 存在未连接节点')
    if len([e for e in flows if e.get('sourceRef') == starts[0].get('id')]) != 1:
        raise ValueError('Start requires one successor / 开始事件必须有一个后继')
    terminals = set()
    successors = {node_id: [edge.get('targetRef') for edge in flows if edge.get('sourceRef') == node_id]
                  for node_id in nodes}
    option_names = {edge.get('id'): edge.get('name') or nodes[edge.get('targetRef')].get('name') or edge.get('targetRef')
                    for edge in flows}
    for node_id, node in nodes.items():
        outgoing = [e for e in flows if e.get('sourceRef') == node_id]
        if node.tag == b('startEvent'):
            continue
        kind = node.get(f('diagnosisKind'))
        if kind not in KINDS:
            raise ValueError('Unknown diagnosis kind / 未知诊断节点: ' + node_id)
        if kind == 'conclusion' and not node.get(f('conclusionText'), '').strip():
            node.set(f('conclusionText'), node.get('name', ''))
        required = {'investigation': ('observation', 'acquisition', 'referenceImage', 'assessment'),
                    'conclusion': ('conclusionText',), 'investigationAction': ('actionText',)}
        if any(not node.get(f(field), '').strip() for field in required.get(kind, ())):
            raise ValueError('Missing required diagnostic content / 诊断内容未填写完整: ' + node_id)
        if kind == 'investigation' and not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}', node.get(f('referenceImage'), '')):
            raise ValueError('Invalid reference image / 无效参考图: ' + node_id)
        if kind in ('problemSolved', 'escalation') and node.get('name') != {'problemSolved': '问题解决', 'escalation': '上升'}[kind]:
            raise ValueError('Final node text is fixed / 最终节点内容固定: ' + node_id)
        if kind in ('problemSolved', 'escalation'):
            if outgoing:
                raise ValueError('Final node has outgoing flow / 最终节点不能有后继')
            terminals.add(node_id)
            if kind == 'escalation':
                # 业务上仍是最终节点；引擎在结束前等待复核，避免结束后无法回退。
                review_id = new_id(node_id + '_review')
                node.tag = b('userTask')
                node.set('id', review_id)
                node.set('name', '上升：等待复核 / Escalation review')
                for edge in flows:
                    if edge.get('targetRef') == node_id:
                        edge.set('targetRef', review_id)
                ET.SubElement(process, b('endEvent'), {'id': node_id, 'name': '上升'})
                ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_confirm'),
                    'sourceRef': review_id, 'targetRef': node_id})
                manifest['reviews'][review_id] = {'nodeId': node_id}
            else:
                node.tag = b('endEvent')
        elif kind == 'jump' and not outgoing:
            terminals.add(node_id)
        elif not outgoing:
            raise ValueError('Missing successor / 缺少后继: ' + node_id)
        if kind == 'conclusion' and len(outgoing) != 1:
            raise ValueError('Conclusion requires one successor / 结论必须有且仅有一个后继')
        module, function = node.get(f('pythonModule'), '').strip(), node.get(f('pythonFunction'), '').strip()
        if kind not in ('problemSolved', 'escalation'):
            human = kind == 'investigation' and node.get(f('humanDecision')) == 'true'
            branches = {}
            if kind == 'investigation':
                for edge in outgoing:
                    branch = edge.get(f('diagnosisBranch')) or {'是': 'yes', '否': 'no', 'yes': 'yes', 'no': 'no'}.get(edge.get('name', '').lower())
                    if branch not in ('yes', 'no'):
                        raise ValueError('Select Yes/No for branch / 请设置是或否分支: ' + edge.get('id'))
                    branches[edge.get('id')] = branch
                if set(branches.values()) != {'yes', 'no'}:
                    raise ValueError('Investigation requires Yes and No / 排查节点需要是和否两种分支: ' + node_id)
            has_python = bool(module or function)
            if kind != 'conclusion' and not human and not has_python:
                raise ValueError('Bind Python interface / 请绑定 Python 接口: ' + node_id)
            if has_python and (not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', module) or not re.fullmatch(r'[A-Za-z_]\w*', function)):
                raise ValueError('Invalid Python interface / 无效 Python 接口: ' + node_id)
            kwargs = json.loads(node.get(f('pythonArguments')) or '{}')
            if not isinstance(kwargs, dict):
                raise ValueError('Arguments must be an object / 参数必须是 JSON 对象')
            topic = f'{process_id}.{version}.' + (node.get(f('pythonTopic'), '').strip() or node_id)
            if topic in manifest['bindings']:
                raise ValueError('Duplicate topic / 重复工作主题: ' + topic)
            manifest['bindings'][topic] = {'nodeId': node_id, 'module': module, 'function': function,
                'kwargs': kwargs, 'outgoing': sorted(e.get('id') for e in outgoing), 'kind': kind,
                'humanDecision': human, 'branches': branches}
            node.tag = b('serviceTask') if has_python else b('userTask') if human else b('task')
            if has_python:
                node.set(f('type'), 'external-worker')
                node.set(f('topic'), topic)
            continuation_id = node_id
            if kind == 'investigation':
                # 引擎只消费组件发出的等待请求；自动结果直接绕过人工任务。
                review_id = new_id(node_id + '_review') if has_python else node_id
                if has_python:
                    ET.SubElement(process, b('userTask'), {'id': review_id,
                        'name': (node.get('name') or node_id) + ' / 人工判断 / Human decision'})
                    wait_id = new_id(node_id + '_wait')
                    resume_id = new_id(node_id + '_resume')
                    ET.SubElement(process, b('exclusiveGateway'), {'id': wait_id})
                    ET.SubElement(process, b('exclusiveGateway'), {'id': resume_id})
                    ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_to_wait'),
                        'sourceRef': node_id, 'targetRef': wait_id})
                    for target, expected in ((review_id, 'true'), (resume_id, 'false')):
                        edge = ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_wait_route'),
                            'sourceRef': wait_id, 'targetRef': target})
                        expression = ET.SubElement(edge, b('conditionExpression'), {
                            '{http://www.w3.org/2001/XMLSchema-instance}type': 'bpmn:tFormalExpression'})
                        expression.text = '${execution.getVariable(' + json.dumps('human_' + node_id) + ') == ' + expected + '}'
                    ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_reviewed'),
                        'sourceRef': review_id, 'targetRef': resume_id})
                    continuation_id = resume_id
                else:
                    continuation_id = review_id
                manifest['reviews'][review_id] = {'nodeId': node_id, 'mode': 'decision',
                    'name': node.get('name') or node_id,
                    'instructions': {field: node.get(f(field), '') for field in
                        ('observation', 'acquisition', 'assessment', 'referenceImage', 'conclusionText', 'actionText')},
                    'options': [{'id': 'yes', 'name': '是 / Yes'}, {'id': 'no', 'name': '否 / No'}]}
            if len(outgoing) > 1:
                gateway_id = new_id(node_id + '_decision')
                ET.SubElement(process, b('inclusiveGateway') if branches else b('parallelGateway'), {'id': gateway_id})
                ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_to_decision'),
                    'sourceRef': continuation_id, 'targetRef': gateway_id})
                for edge in outgoing:
                    edge.set('sourceRef', gateway_id)
                    for condition in list(edge):
                        edge.remove(condition)
                    if branches:
                        expression = ET.SubElement(edge, b('conditionExpression'), {
                            '{http://www.w3.org/2001/XMLSchema-instance}type': 'bpmn:tFormalExpression'})
                        # 同一判断结果的所有出口同时触发，不依赖 XML 中的顺序。
                        expression.text = '${execution.getVariable(' + json.dumps('route_' + node_id) + ') == ' + json.dumps(branches[edge.get('id')]) + '}'
            elif not outgoing:
                end_id = new_id(node_id + '_handoff')
                ET.SubElement(process, b('endEvent'), {'id': end_id, 'name': 'Handoff / 跳转交接'})
                ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_to_handoff'),
                    'sourceRef': continuation_id, 'targetRef': end_id})
            else:
                outgoing[0].set('sourceRef', continuation_id)
        # 业务元数据只保留在原始图；引擎文件只承载执行语义。
        for key in list(node.attrib):
            if key.startswith('{' + FLOWABLE + '}') and key not in (f('type'), f('topic')):
                del node.attrib[key]
        for child in list(node):
            if child.tag in (b('incoming'), b('outgoing')):
                node.remove(child)
    # 拒绝没有最终出口的闭环；有出口的重试环允许存在。
    can_finish = set(terminals)
    while True:
        previous = len(can_finish)
        can_finish.update(n for n, targets in successors.items() if any(t in can_finish for t in targets))
        if len(can_finish) == previous:
            break
    if set(nodes) - can_finish:
        raise ValueError('Chain cannot reach an end / 存在无法到达最终节点的链路')
    for edge in flows:
        edge.attrib.pop(f('diagnosisBranch'), None)
    process.set('isExecutable', 'true')
    # 流程说明在 Flowable 中限制为 2000 字符；执行元数据及参考图放在扩展元素。
    extensions = process.find(b('extensionElements'))
    if extensions is None:
        extensions = ET.Element(b('extensionElements'))
        process.insert(len(process.findall(b('documentation'))), extensions)
    for item in extensions.findall(f('diagnosticExecution')):
        extensions.remove(item)
    # Flowable 的通用扩展文本解析可能覆盖分块字符事件，属性值可完整往返长 JSON。
    ET.SubElement(extensions, f('diagnosticExecution'), {'value': json.dumps(manifest, ensure_ascii=False)})
    for diagram in root.findall('{' + DI + '}BPMNDiagram'):
        root.remove(diagram)
    return {'processId': process_id, 'files': {'source.bpmn': xml,
        'workflow.bpmn20.xml': ET.tostring(root, encoding='unicode', xml_declaration=True),
        'bindings.json': json.dumps(manifest, ensure_ascii=False, indent=2)}}


def engine_request(path, data=None, content_type='application/json'):
    base = os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080').rstrip('/')
    credentials = os.environ.get('FLOWABLE_USER', 'diagnostic') + ':' + os.environ.get('FLOWABLE_PASSWORD', 'local-demo')
    headers = {'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode()}
    if data is not None:
        headers['Content-Type'] = content_type
    try:
        with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
            return json.load(response) if response.status != 204 else {}
    except HTTPError as error:
        raise RuntimeError(f'Flowable HTTP {error.code}: {error.read().decode(errors="replace")}') from error
    except URLError as error:
        raise RuntimeError('Cannot connect to Flowable / 无法连接 Flowable: ' + str(error)) from error


def deploy(xml):
    boundary = uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="workflow.bpmn20.xml"\r\n'
               'Content-Type: application/xml\r\n\r\n' + xml + f'\r\n--{boundary}--\r\n').encode()
    return engine_request('/process-api/repository/deployments', payload, 'multipart/form-data; boundary=' + boundary)
