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
from reference_files import parse_reference_file

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


def node_instructions(node):
    return {field: node.get(f(field), '') for field in
        ('observation', 'acquisition', 'assessment', 'referenceImage', 'referenceImageName',
         'detailText', 'conclusionText', 'actionText')}


def decision_options(manifest, node_id):
    return [{'id': branch, 'name': name, 'paths': [
        {'id': edge['id'], 'name': manifest['nodes'][edge['target']]['name'],
         'target': edge['target']}
        for edge in manifest['nodes'][node_id]['outgoing'] if edge['branch'] == branch]}
        for branch, name in [('yes', '是 / Yes'), ('no', '否 / No')]]


def delegate_fields(element, source, operation):
    extensions = element if element.tag == f('executionListener') else element.find(b('extensionElements'))
    if extensions is None:
        extensions = ET.SubElement(element, b('extensionElements'))
    for name, value in [('source', source), ('operation', operation)]:
        field = ET.SubElement(extensions, f('field'), {'name': name})
        ET.SubElement(field, f('string')).text = value


def serial_workflow(xml, manifest):
    """引擎仍执行原业务任务；只用事务内持久队列替代同时启动的出口。"""
    root = ET.fromstring(xml)
    process = root.find(b('process'))
    originals = {element.get('id'): element for element in process
                 if element.tag in (b('task'), b('startEvent'))}
    instructions = {node_id: node_instructions(node) for node_id, node in originals.items()}
    for element in list(process):
        if element.tag not in (b('task'), b('startEvent'), b('documentation'), b('extensionElements')):
            process.remove(element)
    used = {element.get('id') for element in root.iter() if element.get('id')}
    def unique(stem):
        while stem in used:
            stem += '_'
        used.add(stem)
        return stem
    gateway_id, end_id = unique('diagnostic_dispatch'), unique('diagnostic_end')
    ET.SubElement(process, b('exclusiveGateway'), {'id': gateway_id})
    ET.SubElement(process, b('endEvent'), {'id': end_id})
    manifest['endId'] = end_id
    bindings = {binding['nodeId']: (topic, binding) for topic, binding in manifest['bindings'].items()}
    instructions.update({node_id: binding['instructions']
        for node_id, (_, binding) in bindings.items()})
    manifest['reviews'] = {}
    destinations = []
    def connect(source, target, condition=None):
        edge = ET.SubElement(process, b('sequenceFlow'), {'id': unique(source + '_route'),
            'sourceRef': source, 'targetRef': target})
        if condition:
            ET.SubElement(edge, b('conditionExpression'), {
                '{http://www.w3.org/2001/XMLSchema-instance}type': 'bpmn:tFormalExpression'}).text = condition
    def dispatcher(source, operation='schedule'):
        key = unique(source + '_dispatch')
        element = ET.SubElement(process, b('serviceTask'), {'id': key, f('class'): 'local.diagnosis.DiagnosisScheduler'})
        delegate_fields(element, source, operation)
        connect(key, gateway_id)
        return key
    for node_id, node in originals.items():
        info = manifest['nodes'][node_id]
        kind = info['kind']
        for child in list(node):
            if child.tag in (b('incoming'), b('outgoing')):
                node.remove(child)
        for key in list(node.attrib):
            if key.startswith('{' + FLOWABLE + '}'):
                del node.attrib[key]
        if kind == 'start':
            connect(node_id, dispatcher(node_id))
            continue
        destinations.append(node_id)
        extensions = node.find(b('extensionElements'))
        if extensions is None:
            extensions = ET.SubElement(node, b('extensionElements'))
        listener = ET.SubElement(extensions, f('executionListener'), {'event': 'start', 'class': 'local.diagnosis.DiagnosisScheduler'})
        delegate_fields(listener, node_id, 'visit')
        continuation = node_id
        if kind == 'problemSolved':
            node.tag = b('task')
            review_id = unique(node_id + '_success_review')
            info['successReview'] = review_id
            ET.SubElement(process, b('userTask'), {'id': review_id, 'name': info['name']})
            manifest['reviews'][review_id] = {'nodeId': node_id, 'mode': 'success', 'name': info['name'],
                'instructions': {**instructions[node_id], 'detailText': info['detailText']},
                'options': [{'id': 'continue', 'name': '继续排查 / Continue'}, {'id': 'finish', 'name': '结束排查 / Finish'}]}
            destinations.append(review_id)
            connect(review_id, dispatcher(node_id, 'resume'))
        elif kind == 'escalation':
            node.tag = b('userTask')
            manifest['reviews'][node_id] = {'nodeId': node_id, 'mode': 'escalation', 'name': info['name'],
                'instructions': {**instructions[node_id], 'detailText': info['detailText']}}
        else:
            topic, binding = bindings[node_id]
            has_python, human = bool(binding['module']), binding['humanDecision']
            node.tag = b('serviceTask') if has_python else b('userTask') if human else b('task')
            if has_python:
                node.set(f('type'), 'external-worker')
                node.set(f('topic'), topic)
            if kind == 'investigation':
                review_id = unique(node_id + '_review') if has_python else node_id
                manifest['reviews'][review_id] = {'nodeId': node_id, 'mode': 'decision', 'name': info['name'],
                    'selectionMode': 'single', 'options': decision_options(manifest, node_id)}
                manifest['reviews'][review_id]['instructions'] = instructions[node_id]
                if has_python:
                    ET.SubElement(process, b('userTask'), {'id': review_id, 'name': info['name'] + ' / Human decision'})
                    wait_id, resume_id = unique(node_id + '_wait'), unique(node_id + '_resume')
                    ET.SubElement(process, b('exclusiveGateway'), {'id': wait_id})
                    ET.SubElement(process, b('exclusiveGateway'), {'id': resume_id})
                    connect(node_id, wait_id)
                    connect(wait_id, review_id, '${execution.getVariable(' + json.dumps('human_' + node_id) + ') == true}')
                    connect(wait_id, resume_id, '${execution.getVariable(' + json.dumps('human_' + node_id) + ') == false}')
                    connect(review_id, resume_id)
                    continuation = resume_id
        connect(continuation, dispatcher(node_id))
    for destination in destinations + [end_id]:
        connect(gateway_id, destination, '${execution.getVariable("diagnosticNext") == ' + json.dumps(destination) + '}')
    return root, process


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
    # 工作主题取决于执行定义；串行分支顺序属于调度语义，布局与说明不属于。
    mode = process.get(f('diagnosisMode'), 'parallel')
    if mode not in ('parallel', 'serial'):
        raise ValueError('Invalid diagnosis mode / 无效排查模式')
    signature = {'formatVersion': 8, 'processId': process_id, 'mode': mode, 'nodes': [], 'flows': []}
    executable_elements = [e for e in process if e.tag in (b('task'), b('startEvent'), b('sequenceFlow'))]
    execution_ids = [e.get('id') for e in executable_elements]
    if any(not value for value in execution_ids) or len(set(execution_ids)) != len(execution_ids):
        raise ValueError('Missing or duplicate element ID / 元素 ID 缺失或重复')
    for element in executable_elements:
        if element.get('default') or element.find(b('conditionExpression')) is not None:
            raise ValueError('Use the Python next result instead of flow conditions / 请使用 Python 的 next 返回值选择分支，并移除条件表达式和默认分支: ' + element.get('id'))
        if element.tag == b('sequenceFlow'):
            signature['flows'].append([element.get('id'), element.get('sourceRef'), element.get('targetRef'), element.get(f('diagnosisBranch')), element.get(f('diagnosisOrder'))])
        else:
            kwargs = json.loads(element.get(f('pythonArguments')) or '{}')
            if not isinstance(kwargs, dict):
                raise ValueError('Arguments must be an object / 参数必须是 JSON 对象')
            signature['nodes'].append({'id': element.get('id'), 'kind': element.get(f('diagnosisKind')),
                'module': element.get(f('pythonModule'), '').strip(),
                'factory': element.get(f('pythonFactory'), '').strip(),
                'function': element.get(f('pythonFunction'), '').strip(), 'kwargs': kwargs,
                'topic': element.get(f('pythonTopic'), '').strip(),
                'humanDecision': element.get(f('humanDecision')) == 'true'})
    signature['nodes'].sort(key=lambda item: item['id'])
    # 串行模式保留缺省/同优先级连线的 XML 顺序，顺序本身也是执行定义。
    if mode == 'parallel':
        signature['flows'].sort(key=lambda edge: edge[0])
    version = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()[:12]
    manifest = {'processId': process_id, 'version': version, 'bindings': {}, 'reviews': {}, 'mode': mode, 'nodes': {}}
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
    for node_id, node in nodes.items():
        outgoing = [edge for edge in flows if edge.get('sourceRef') == node_id]
        try:
            outgoing = sorted(outgoing, key=lambda edge: int(edge.get(f('diagnosisOrder'), '0')))
        except ValueError as error:
            raise ValueError('Invalid diagnosis order / 无效排查顺序: ' + node_id) from error
        manifest['nodes'][node_id] = {'id': node_id, 'name': node.get('name') or node_id,
            'kind': node.get(f('diagnosisKind'), 'start'),
            'detailText': node.get(f('detailText')) or node.get(f('actionText')) or node.get(f('conclusionText'), ''),
            'outgoing': [{'id': edge.get('id'), 'target': edge.get('targetRef'),
                'branch': edge.get(f('diagnosisBranch')) or {'是': 'yes', '否': 'no', 'yes': 'yes', 'no': 'no'}.get(edge.get('name', '').lower())}
                for edge in outgoing]}
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
        if node.get(f('detailText'), '').strip():
            if kind == 'conclusion':
                node.set(f('conclusionText'), node.get(f('detailText')))
            if kind == 'investigationAction':
                node.set(f('actionText'), node.get(f('detailText')))
        if kind == 'conclusion' and not node.get(f('conclusionText'), '').strip():
            node.set(f('conclusionText'), node.get('name', ''))
        required = {'investigation': ('observation', 'acquisition', 'referenceImage', 'assessment'),
                    'conclusion': ('conclusionText',), 'investigationAction': ('actionText',)}
        if any(not node.get(f(field), '').strip() for field in required.get(kind, ())):
            raise ValueError('Missing required diagnostic content / 诊断内容未填写完整: ' + node_id)
        if kind == 'investigation':
            # 与编辑器保持同一文件协议；严格解码避免把坏附件部署成可用参考资料。
            try:
                parse_reference_file(node.get(f('referenceImage'), ''))
            except ValueError as error:
                raise ValueError('Invalid reference file (maximum 50 MiB) / 无效参考文件（最大 50 MiB）: ' + node_id) from error
        if kind in ('problemSolved', 'escalation'):
            if outgoing:
                raise ValueError('Final node has outgoing flow / 最终节点不能有后继')
            terminals.add(node_id)
            if kind == 'escalation':
                # 业务上仍是最终节点；引擎在结束前等待复核，避免结束后无法回退。
                review_id = new_id(node_id + '_review')
                node.tag = b('userTask')
                node.set('id', review_id)
                node.set('name', (node.get('name') or node_id) + ' / 等待复核 / Escalation review')
                for edge in flows:
                    if edge.get('targetRef') == node_id:
                        edge.set('targetRef', review_id)
                ET.SubElement(process, b('endEvent'), {'id': node_id, 'name': manifest['nodes'][node_id]['name']})
                ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_confirm'),
                    'sourceRef': review_id, 'targetRef': node_id})
                manifest['reviews'][review_id] = {'nodeId': node_id, 'name': manifest['nodes'][node_id]['name'],
                    'instructions': {**node_instructions(node),
                        'detailText': manifest['nodes'][node_id]['detailText']}}
            else:
                node.tag = b('endEvent')
        elif kind == 'jump' and not outgoing:
            terminals.add(node_id)
        elif not outgoing:
            if kind == 'investigation':
                terminals.add(node_id)
            else:
                raise ValueError('Missing successor / 缺少后继: ' + node_id)
        if kind == 'conclusion' and len(outgoing) != 1:
            raise ValueError('Conclusion requires one successor / 结论必须有且仅有一个后继')
        module, function = node.get(f('pythonModule'), '').strip(), node.get(f('pythonFunction'), '').strip()
        factory = node.get(f('pythonFactory'), '').strip()
        if kind not in ('problemSolved', 'escalation'):
            human = kind == 'investigation' and node.get(f('humanDecision')) == 'true'
            branches = {}
            if kind == 'investigation':
                for edge in outgoing:
                    branch = edge.get(f('diagnosisBranch')) or {'是': 'yes', '否': 'no', 'yes': 'yes', 'no': 'no'}.get(edge.get('name', '').lower())
                    if branch not in ('yes', 'no'):
                        raise ValueError('Select Yes/No for branch / 请设置是或否分支: ' + edge.get('id'))
                    branches[edge.get('id')] = branch
            has_python = bool(module or function)
            if kind != 'conclusion' and not human and not has_python:
                raise ValueError('Bind Python interface / 请绑定 Python 接口: ' + node_id)
            if has_python and (not re.fullmatch(r'[A-Za-z_]\w*(\.[A-Za-z_]\w*)*', module) or not re.fullmatch(r'[A-Za-z_]\w*', function)):
                raise ValueError('Invalid Python interface / 无效 Python 接口: ' + node_id)
            if factory and (not has_python or not all(part.isidentifier() and not part.startswith('_') for part in factory.split('.'))):
                raise ValueError('Invalid Python factory / 无效 Python 实例入口: ' + node_id)
            kwargs = json.loads(node.get(f('pythonArguments')) or '{}')
            if not isinstance(kwargs, dict):
                raise ValueError('Arguments must be an object / 参数必须是 JSON 对象')
            topic = f'{process_id}.{version}.' + (node.get(f('pythonTopic'), '').strip() or node_id)
            if topic in manifest['bindings']:
                raise ValueError('Duplicate topic / 重复工作主题: ' + topic)
            manifest['bindings'][topic] = {'nodeId': node_id, 'module': module, 'function': function,
                'factory': factory,
                'kwargs': kwargs, 'outgoing': sorted(e.get('id') for e in outgoing), 'kind': kind,
                'humanDecision': human, 'branches': branches, 'mode': mode,
                'instructions': node_instructions(node),
                'detailText': manifest['nodes'][node_id]['detailText']}
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
                    'instructions': node_instructions(node),
                    'selectionMode': 'single', 'options': decision_options(manifest, node_id)}
            if len(outgoing) > 1 or kind == 'investigation':
                gateway_id = new_id(node_id + '_decision')
                gateway = ET.SubElement(process, b('inclusiveGateway') if kind == 'investigation' else b('parallelGateway'), {'id': gateway_id})
                if kind == 'investigation':
                    failure_id = new_id(node_id + '_failed')
                    failure_flow = new_id(node_id + '_unmatched')
                    gateway.set('default', failure_flow)
                    failure = ET.SubElement(process, b('serviceTask'), {'id': failure_id, f('class'): 'local.diagnosis.DiagnosisScheduler'})
                    delegate_fields(failure, node_id, 'failure')
                    end_id = new_id(node_id + '_failure_end')
                    ET.SubElement(process, b('endEvent'), {'id': end_id})
                    ET.SubElement(process, b('sequenceFlow'), {'id': failure_flow, 'sourceRef': gateway_id, 'targetRef': failure_id})
                    ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_failed_end'), 'sourceRef': failure_id, 'targetRef': end_id})
                ET.SubElement(process, b('sequenceFlow'), {'id': new_id(node_id + '_to_decision'),
                    'sourceRef': continuation_id, 'targetRef': gateway_id})
                for edge in outgoing:
                    edge.set('sourceRef', gateway_id)
                    for condition in list(edge):
                        edge.remove(condition)
                    if branches:
                        expression = ET.SubElement(edge, b('conditionExpression'), {
                            '{http://www.w3.org/2001/XMLSchema-instance}type': 'bpmn:tFormalExpression'})
                        # 自动判断缺省执行全组；人工可在同组内只启动所选连线。
                        selection = 'execution.getVariable(' + json.dumps('selectedRoutes_' + node_id) + ')'
                        expression.text = ('${execution.getVariable(' + json.dumps('route_' + node_id)
                            + ') == ' + json.dumps(branches[edge.get('id')]) + ' && (' + selection
                            + ' == null || ' + selection + '.isNull() || ' + selection
                            + '.has(' + json.dumps(edge.get('id')) + '))}')
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
    if mode == 'serial':
        root, process = serial_workflow(xml, manifest)
    else:
        for node_id, original in nodes.items():
            if original.tag != b('startEvent'):
                extensions = original.find(b('extensionElements'))
                if extensions is None:
                    extensions = ET.SubElement(original, b('extensionElements'))
                listener = ET.SubElement(extensions, f('executionListener'), {'event': 'start', 'class': 'local.diagnosis.DiagnosisScheduler'})
                delegate_fields(listener, node_id, 'visit')
                if manifest['nodes'][node_id]['kind'] in ('problemSolved', 'escalation', 'jump'):
                    listener = ET.SubElement(extensions, f('executionListener'), {'event': 'end', 'class': 'local.diagnosis.DiagnosisScheduler'})
                    delegate_fields(listener, node_id, 'success' if manifest['nodes'][node_id]['kind'] == 'problemSolved' else 'outcome')
    for edge in process.findall(b('sequenceFlow')):
        edge.attrib.pop(f('diagnosisBranch'), None)
        edge.attrib.pop(f('diagnosisOrder'), None)
    process.set('isExecutable', 'true')
    # 流程说明在 Flowable 中限制为 2000 字符；执行元数据及参考图放在扩展元素。
    extensions = process.find(b('extensionElements'))
    if extensions is None:
        extensions = ET.Element(b('extensionElements'))
        process.insert(len(process.findall(b('documentation'))), extensions)
    if mode == 'parallel':
        for event, operation in [('start', 'initialize'), ('end', 'complete')]:
            listener = ET.SubElement(extensions, f('executionListener'), {'event': event, 'class': 'local.diagnosis.DiagnosisScheduler'})
            delegate_fields(listener, '', operation)
    for item in extensions.findall(f('diagnosticExecution')):
        extensions.remove(item)
    # Flowable 的通用扩展文本解析可能覆盖分块字符事件，属性值可完整往返长 JSON。
    ET.SubElement(extensions, f('diagnosticExecution'), {'value': json.dumps(manifest, ensure_ascii=False)})
    for diagram in root.findall('{' + DI + '}BPMNDiagram'):
        root.remove(diagram)
    return {'processId': process_id, 'files': {'source.bpmn': xml,
        'workflow.bpmn20.xml': ET.tostring(root, encoding='unicode', xml_declaration=True),
        'bindings.json': json.dumps(manifest, ensure_ascii=False, indent=2)}}


def engine_request(path, data=None, content_type='application/json', as_text=False):
    base = os.environ.get('FLOWABLE_URL', 'http://127.0.0.1:8080').rstrip('/')
    credentials = os.environ.get('FLOWABLE_USER', 'diagnostic') + ':' + os.environ.get('FLOWABLE_PASSWORD', 'local-demo')
    headers = {'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode()}
    if data is not None:
        headers['Content-Type'] = content_type
    try:
        with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
            if response.status == 204:
                return {}
            return response.read().decode('utf-8', errors='replace') if as_text else json.load(response)
    except HTTPError as error:
        raise RuntimeError(f'Flowable HTTP {error.code}: {error.read().decode(errors="replace")}') from error
    except URLError as error:
        raise RuntimeError('Cannot connect to Flowable / 无法连接 Flowable: ' + str(error)) from error


def deploy(xml):
    boundary = uuid.uuid4().hex
    payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="workflow.bpmn20.xml"\r\n'
               'Content-Type: application/xml\r\n\r\n' + xml + f'\r\n--{boundary}--\r\n').encode()
    return engine_request('/process-api/repository/deployments', payload, 'multipart/form-data; boundary=' + boundary)
