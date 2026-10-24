import acquisition from './templates/acquisition.py?raw'
import parsing from './templates/parsing.py?raw'
import display from './templates/display.py?raw'
import diagnosis from './templates/diagnosis.py?raw'
import diagnosticComponents from '/backend/diagnostic_components.py?raw'
import actions from './templates/actions.py?raw'
import routing from './templates/routing.py?raw'
import runner from './templates/runner.py?raw'
import { diagnosisKinds, isReferenceImage } from '@/views/ProcessDesigner/Diagnosis/model'
import { translateUi } from '@/languages/uiText'

// Moddle 是外部边界；只读取导出所需属性，不修改流程模型。
export interface ModelElement {
  $type: string
  id: string
  get: (property: string) => unknown
}
interface Edge {
  id: string
  name: string
  condition: string
  target: string
  targetName: string
  default: boolean
}
interface Node {
  id: string
  name: string
  kind: string
  scope: string
  start?: string
  observation: string
  acquisition: string
  assessment: string
  referenceImage: string
  actionText: string
  conclusionText: string
  documentation: string
  outgoing: Edge[]
}
export type ProjectFiles = Record<string, string | Uint8Array>
const text = (element: ModelElement, key: string): string => String(element.get(key) ?? '')
const list = (element: ModelElement, key: string): ModelElement[] =>
  (element.get(key) as ModelElement[] | undefined) ?? []

export function generateProject(definitions: ModelElement, xml: string): ProjectFiles {
  const errors: string[] = []
  const fail = (id: string, zh: string, en: string) => errors.push(`${id}: ${translateUi(zh, en)}`)
  const processes = list(definitions, 'rootElements').filter((e) => e.$type === 'bpmn:Process')
  for (const root of list(definitions, 'rootElements')) {
    if (root.$type === 'bpmn:Collaboration' && list(root, 'messageFlows').length) {
      fail(root.id, '暂不支持跨流程消息流', 'Message flows between processes are unsupported')
    }
  }
  if (processes.length !== 1) {
    throw new Error(translateUi('导出要求恰好一个流程。', 'Export requires exactly one process.'))
  }
  const nodes: Record<string, Node> = Object.create(null)
  const files: ProjectFiles = { 'source.bpmn': xml }
  let imageIndex = 0
  const readScope = (scope: ModelElement): string => {
    const elements = list(scope, 'flowElements')
    const starts = elements.filter((e) => e.$type === 'bpmn:StartEvent')
    if (starts.length !== 1)
      fail(scope.id, '需要且只能有一个开始事件', 'Exactly one start event is required')
    for (const element of elements) {
      if (element.$type === 'bpmn:SequenceFlow') continue
      const kind = text(element, 'flowable:diagnosisKind')
      const builtin: Record<string, string> = {
        'bpmn:StartEvent': 'start',
        'bpmn:EndEvent': 'end',
        'bpmn:ExclusiveGateway': 'gateway',
        'bpmn:SubProcess': 'subprocess',
      }
      const supportedKind =
        element.$type === 'bpmn:Task' && Object.prototype.hasOwnProperty.call(diagnosisKinds, kind)
      if (!supportedKind && !builtin[element.$type]) {
        fail(element.id, `暂不支持 ${element.$type}`, `Unsupported element ${element.$type}`)
        continue
      }
      if (
        list(element, 'eventDefinitions').length ||
        element.get('loopCharacteristics') ||
        element.get('triggeredByEvent') ||
        element.get('isForCompensation')
      ) {
        fail(
          element.id,
          '不支持事件触发、多实例或补偿语义',
          'Event-triggered, multi-instance and compensation semantics are unsupported',
        )
      }
      const node: Node = {
        id: element.id,
        name: text(element, 'name') || element.id,
        kind: supportedKind ? kind : builtin[element.$type]!,
        scope: scope.id,
        observation: text(element, 'flowable:observation'),
        acquisition: text(element, 'flowable:acquisition'),
        assessment: text(element, 'flowable:assessment'),
        referenceImage: '',
        actionText: text(element, 'flowable:actionText'),
        conclusionText: text(element, 'flowable:conclusionText'),
        documentation: list(element, 'documentation')
          .map((d) => text(d, 'text'))
          .join('\n'),
        outgoing: [],
      }
      if (nodes[node.id]) fail(node.id, '节点 ID 重复', 'Duplicate node ID')
      nodes[node.id] = node
      if (node.kind === 'investigation') {
        if (![node.observation, node.acquisition, node.assessment].every((v) => v.trim())) {
          fail(
            node.id,
            '请填写查看数据、获取方法及判断方法',
            'Complete observation, acquisition and assessment',
          )
        }
        const image = text(element, 'flowable:referenceImage')
        if (!isReferenceImage(image)) {
          fail(node.id, '缺少有效参考图', 'A valid reference image is required')
        } else {
          const extension = image.slice(11, image.indexOf(';'))
          const path = `images/reference_${++imageIndex}.${extension}`
          files[path] = Uint8Array.from(atob(image.slice(image.indexOf(',') + 1)), (c) =>
            c.charCodeAt(0),
          )
          node.referenceImage = path
        }
      }
      if (node.kind === 'conclusion' && !node.conclusionText.trim())
        fail(node.id, '缺少结论内容', 'Conclusion text is required')
      if (node.kind === 'investigationAction' && !node.actionText.trim())
        fail(node.id, '缺少排查动作内容', 'Investigation action text is required')
      if (node.kind === 'subprocess') node.start = readScope(element)
    }
    for (const flow of elements.filter((e) => e.$type === 'bpmn:SequenceFlow')) {
      const source = nodes[(flow.get('sourceRef') as ModelElement | undefined)?.id ?? '']
      const target = nodes[(flow.get('targetRef') as ModelElement | undefined)?.id ?? '']
      if (!source || !target || source.scope !== scope.id || target.scope !== scope.id) {
        fail(flow.id, '连线端点无效或跨越子流程边界', 'Invalid endpoints or cross-scope flow')
        continue
      }
      const condition = flow.get('conditionExpression') as ModelElement | undefined
      source.outgoing.push({
        id: flow.id,
        name: text(flow, 'name'),
        condition: condition ? text(condition, 'body') : '',
        target: target.id,
        targetName: target.name,
        default:
          (elements.find((e) => e.id === source.id)?.get('default') as ModelElement | undefined)
            ?.id === flow.id,
      })
    }
    return starts[0]?.id ?? ''
  }
  const start = readScope(processes[0]!)
  const terminals = new Set(['problemSolved', 'escalation', 'jump'])
  for (const node of Object.values(nodes)) {
    if (node.kind === 'end' && node.scope === processes[0]!.id)
      fail(
        node.id,
        '顶层必须以问题解决、上升或跳转结束',
        'Top-level paths must end at Problem Solved, Escalation or Jump',
      )
    if (terminals.has(node.kind) || node.kind === 'end') {
      if (node.outgoing.length)
        fail(
          node.id,
          '终止或跳转节点不能带后续连线',
          'Terminal/handoff nodes cannot have outgoing flows',
        )
    } else if (!node.outgoing.length) fail(node.id, '缺少后续连线', 'Missing outgoing flow')
    if (
      node.kind === 'conclusion' &&
      (node.outgoing.length !== 1 ||
        !['remediation', 'jump', 'escalation'].includes(
          nodes[node.outgoing[0]?.target ?? '']?.kind ?? '',
        ))
    )
      fail(
        node.id,
        '结论必须连接一个处理动作或上升',
        'Conclusion must lead to one handling action or escalation',
      )
  }
  // 可达性检查独立于编辑器的可开关校验，避免导出断链和无出口的循环。
  const reachable = new Set<string>()
  const visit = (id: string) => {
    if (reachable.has(id) || !nodes[id]) return
    reachable.add(id)
    const node = nodes[id]!
    if (node.start) visit(node.start)
    node.outgoing.forEach((e) => visit(e.target))
  }
  visit(start)
  const canFinish = new Set(
    Object.values(nodes)
      .filter((n) => terminals.has(n.kind) || (n.kind === 'end' && n.scope !== processes[0]!.id))
      .map((n) => n.id),
  )
  let changed = true
  while (changed) {
    changed = false
    for (const node of Object.values(nodes)) {
      if (!canFinish.has(node.id) && node.outgoing.some((e) => canFinish.has(e.target))) {
        canFinish.add(node.id)
        changed = true
      }
    }
  }
  for (const node of Object.values(nodes)) {
    if (!reachable.has(node.id))
      fail(node.id, '节点从开始事件不可达', 'Node is unreachable from the start')
    if (!canFinish.has(node.id))
      fail(node.id, '链路没有可达的终止节点', 'No reachable terminal for this path')
  }
  if (errors.length) throw new Error(errors.join('\n'))
  files['workflow.json'] = JSON.stringify({ version: 1, start, nodes }, null, 2)
  files['runner.py'] = runner
  files['routing.py'] = routing
  files['diagnostic_components.py'] = diagnosticComponents
  const investigations = Object.values(nodes).filter((n) => n.kind === 'investigation')
  const actionNodes = Object.values(nodes).filter((n) =>
    ['investigationAction', 'remediation', 'deepDiagnosis'].includes(n.kind),
  )
  const scaffold = (template: string, selected: Node[], args: string, body: string) => {
    const functions = selected
      .map((_, i) => `\n\ndef node_${i + 1}(${args}):\n    ${body}\n`)
      .join('')
    const mapping = selected.map((n, i) => `    ${JSON.stringify(n.id)}: node_${i + 1},`).join('\n')
    return `${template}${functions}\n\nHANDLERS = {\n${mapping}\n}\n`
  }
  files['acquisition.py'] = scaffold(
    acquisition,
    investigations,
    'node, context',
    'raise NotImplementedError("Implement automatic acquisition")',
  )
  files['parsing.py'] = scaffold(parsing, investigations, 'raw, node, context', 'return raw')
  files['display.py'] = scaffold(
    display,
    investigations,
    'data, node, context',
    'default_display(data, node, context)',
  )
  files['diagnosis.py'] = scaffold(
    diagnosis,
    investigations,
    'data, node, context',
    'raise NotImplementedError("Return an outgoing flow ID")',
  )
  files['actions.py'] = scaffold(
    actions,
    actionNodes,
    'node, context',
    'raise NotImplementedError("Implement the machine action")',
  )
  files['inputs.example.json'] = JSON.stringify(
    Object.fromEntries(
      investigations.map((n) => [n.id, { value: 'replace with actual data / 替换为实际数据' }]),
    ),
    null,
    2,
  )
  files['README.md'] = `# Diagnostic workflow / 诊断链路代码骨架

Python 3.10+，仅标准库，无需 pip、服务器或 AI。Python 3.10+, standard library only.

解压后执行 / Run after extraction:

    python runner.py
    python runner.py --data inputs.json --no-images

复制 inputs.example.json 为 inputs.json 并替换示例值。只传入已知数据的节点 ID；其余节点会执行自动获取或提示人工获取。
Copy inputs.example.json to inputs.json, replace sample values, and remove unknown entries.

## 模块 / Modules

- acquisition.py: 拉取数据；未实现时显示 observation/acquisition 并接受 JSON、文本或 @JSON文件路径。
- parsing.py: 解析与校验原始数据，默认原样返回。
- display.py: 展示解析数据，默认打印并通过本地浏览器打开参考图（--no-images 关闭）。
- diagnosis.py: 自动诊断返回当前节点的后续连线 ID；未实现时显示 assessment，人工决定下一步。
- routing.py: 校验返回的连线 ID 或人工选择；条件文本仅展示，不执行、不推断。
- actions.py: 机台/处理动作；未实现时必须输入 yes 确认完成，否则停止。
- runner.py: 顺序调度、子流程进入/返回、执行历史和循环步数限制。
- workflow.json / source.bpmn / images/: 原始说明、完整源图和参考图，独立于代码保存。

每个模块底部 HANDLERS 映射节点 ID 到 node_N 函数，在对应函数内填充逻辑。
Fill the node_N functions linked by each module's HANDLERS mapping.
Only NotImplementedError triggers manual fallback; other exceptions stop execution.
仅 NotImplementedError 触发人工兜底，自动逻辑运行错误不会伪装成成功。

## 程序接口 / Python API

    from runner import run, Context
    result = run(supplied={"实际节点ID": {"voltage": 24}},
                 context=Context(open_images=False))

Context.ask / Context.show 可替换以连接自己的界面；Context.data 保存原始数据、解析结果和诊断结果。
Provide ask/show callbacks for another UI; context.data keeps raw/parsed data and results.
run 返回 status: problemSolved / escalation / jump，jump 表示需要转交其他链路，不表示问题已解决。
Jump is a handoff: no destination is currently stored in the editor; integrate external routing explicitly.

## 支持范围 / Scope

支持本项目诊断节点、普通开始事件、排他选择及嵌套普通子流程；子流程普通结束事件返回父流程。
问题解决/上升会终止整个诊断。多个出口按互斥分支处理；不会并行执行。
条件表达式只供人工阅读；自动判断须在 diagnosis.py 返回连线 ID。默认流不自动猜测。
并行/包容网关、事件定义、多实例、普通任务、消息/跨流程连接等不支持时拒绝导出。
循环允许，但默认最多 1000 步（--max-steps）；自动函数自身的超时由实现者负责。
Supported: diagnostic nodes, plain starts, exclusive branches and nested plain subprocesses.
Unsupported BPMN constructs are rejected. Conditions are never evaluated as code.

重新导出到新目录，再迁移函数实现；不要覆盖已填写的业务代码。节点 ID 是数据与实现的关联键。
Regenerate into a NEW directory and migrate implementations; keep node IDs stable.
`
  return files
}
