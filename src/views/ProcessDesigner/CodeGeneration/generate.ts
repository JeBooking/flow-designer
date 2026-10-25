import acquisition from './templates/acquisition.py?raw'
import parsing from './templates/parsing.py?raw'
import display from './templates/display.py?raw'
import diagnosis from './templates/diagnosis.py?raw'
import diagnosticComponents from '/backend/diagnostic_components.py?raw'
import actions from './templates/actions.py?raw'
import routing from './templates/routing.py?raw'
import runner from './templates/runner.py?raw'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import {
  diagnosisKinds,
  isReferenceFile,
  isDiagnosisConnectionAllowed,
  getDiagnosisBranch,
} from '@/views/ProcessDesigner/Diagnosis/model'
import { translateUi } from '@/languages/uiText'
import { generateWorkflowProject } from '@/views/ProcessDesigner/CodeGeneration/workflowDefinition'

// Moddle 是外部边界；只读取导出所需属性，不修改流程模型。
export interface ModelElement {
  $type: string
  id: string
  get: (property: string) => unknown
}
interface Edge {
  id: string
  name: string
  branch: string
  order: number
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
  detailText: string
  actionText: string
  conclusionText: string
  documentation: string
  outgoing: Edge[]
}
export type ProjectFiles = Record<string, string | Uint8Array>
const text = (element: ModelElement, key: string): string => String(element.get(key) ?? '')
const list = (element: ModelElement, key: string): ModelElement[] =>
  (element.get(key) as ModelElement[] | undefined) ?? []

export function generateProject(definitions: ModelElement): ProjectFiles {
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
  const files: ProjectFiles = {}
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
        detailText:
          text(element, 'flowable:detailText') ||
          text(element, 'flowable:actionText') ||
          text(element, 'flowable:conclusionText'),
        actionText: text(element, 'flowable:detailText') || text(element, 'flowable:actionText'),
        conclusionText:
          text(element, 'flowable:detailText') ||
          text(element, 'flowable:conclusionText') ||
          (kind === 'conclusion' ? text(element, 'name') : ''),
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
        if (!isReferenceFile(image)) {
          fail(node.id, '缺少有效参考文件', 'A valid reference file is required')
        } else {
          node.referenceImage = image
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
      if (
        !isDiagnosisConnectionAllowed(
          flow.get('sourceRef') as ModdleElement,
          flow.get('targetRef') as ModdleElement,
        )
      )
        fail(flow.id, '诊断连接违反规则', 'Diagnostic connection violates rules')
      const condition = flow.get('conditionExpression') as ModelElement | undefined
      source.outgoing.push({
        id: flow.id,
        name: text(flow, 'name'),
        branch: getDiagnosisBranch(flow as ModdleElement) || '',
        order: Number(flow.get('flowable:diagnosisOrder') ?? 0),
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
    if (
      node.kind === 'investigation' &&
      node.outgoing.some((edge) => !['yes', 'no'].includes(edge.branch))
    )
      fail(
        node.id,
        '排查连线必须设置是或否分支',
        'Investigation outgoing flows require a Yes or No branch',
      )
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
    } else if (!node.outgoing.length && node.kind !== 'investigation')
      fail(node.id, '缺少后续连线', 'Missing outgoing flow')
    if (node.outgoing.some((edge) => !Number.isInteger(edge.order)))
      fail(node.id, '排查顺序必须为整数', 'Diagnosis order must be an integer')
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
      .filter(
        (n) =>
          terminals.has(n.kind) ||
          (n.kind === 'investigation' && !n.outgoing.length) ||
          (n.kind === 'end' && n.scope !== processes[0]!.id),
      )
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
  const mode = text(processes[0]!, 'flowable:diagnosisMode') || 'parallel'
  if (!['parallel', 'serial'].includes(mode))
    throw new Error(translateUi('无效排查模式', 'Invalid diagnosis mode'))
  Object.assign(files, generateWorkflowProject(definitions))
  files['runner.py'] = runner
  files['routing.py'] = routing
  files['diagnostic_components.py'] = diagnosticComponents
  const investigations = Object.values(nodes).filter((n) => n.kind === 'investigation')
  const actionNodes = Object.values(nodes).filter((n) =>
    ['investigationAction', 'remediation', 'deepDiagnosis'].includes(n.kind),
  )
  const contracts: Record<string, { call: string; input: string; output: string; todo: string }> = {
    'acquisition.py': {
      call: 'runner.run → acquisition.fetch → 本函数 → parsing.parse（parsing.py）',
      input:
        'node 为 workflow.json 中此节点的运行视图；context 为 runner.Context。supplied 中有此节点 ID 时跳过本函数。',
      output: '返回原始采样数据 raw，交给 parsing.py 同节点函数；不要在此选择分支。',
      todo: '接入真实采集接口；保留 NotImplementedError 时展示获取方法并人工输入数据。',
    },
    'parsing.py': {
      call: 'acquisition.fetch（acquisition.py）→ parsing.parse → 本函数 → display.display / diagnosis.diagnose',
      input: 'raw 来自 acquisition.py 或 supplied / --data；node / context 与采集阶段相同。',
      output: '返回解析数据 data，同时传给 display.py 和 diagnosis.py；默认原样返回 raw。',
      todo: '按此节点的数据格式补充解析、单位转换和校验；格式错误应抛出具体异常。',
    },
    'display.py': {
      call: 'parsing.parse（parsing.py）→ display.display → 本函数 → diagnosis.diagnose（diagnosis.py）',
      input: 'data 为 parsing.py 的结果；node.referenceImage 是相对 workflow.json 的参考文件路径。',
      output: '返回值不参与路由；默认输出数据与参考文件位置，可替换为业务图表。',
      todo: '需要业务图表时替换 default_display；由 context.show 接入自己的界面。',
    },
    'diagnosis.py': {
      call: 'display.display（display.py）→ diagnosis.diagnose → decision 装饰器 → 本函数 → routing.decide（routing.py）',
      input: 'data 为 parsing.py 的结果；context.data 保存已完成节点的 raw / parsed / result。',
      output:
        '返回 True / False、yes / no 或 {"next": "yes" | "no"}；兼容出口连线 ID，选择该线所属整个分组。',
      todo: '实现 assessment 描述的业务判断；仅 NotImplementedError 触发人工是/否选择，其他异常停止执行。',
    },
    'actions.py': {
      call: 'runner.run → actions.execute → 本函数 → routing.decide（routing.py）→ 后继节点',
      input: 'node 为当前动作定义；context.data 可读取已完成节点结果，外部副作用由业务实现负责。',
      output: '正常返回表示动作已完成，返回值不用于分支；同节点的全部后继继续调度。',
      todo: '实现真实机台/处理动作并考虑重试幂等；仅 NotImplementedError 转人工完成确认，输入 yes 后继续。',
    },
  }
  const commentLines = (label: string, value: string) =>
    `${label}: ${value || '（未填写）'}`.split(/\r\n?|\n/).map((line) => `    # ${line}`)
  const scaffold = (
    filename: string,
    template: string,
    selected: Node[],
    args: string,
    body: string,
  ) => {
    const contract = contracts[filename]!
    const functions = selected
      .map((node, i) => {
        const details = [
          ['实现位置', `${filename}:node_${i + 1}；HANDLERS[${JSON.stringify(node.id)}]`],
          ['节点 ID', node.id],
          ['节点类型', node.kind],
          ['节点名称', node.name],
          ['所属流程/子流程', node.scope],
          ['详细内容', node.detailText],
          ['查看数据', node.observation],
          ['获取方法', node.acquisition],
          ['判断方法', node.assessment],
          ['说明文档', node.documentation],
          ['调用关系', contract.call],
          ['输入', contract.input],
          ['输出', contract.output],
          ['待补业务', contract.todo],
          ['分支约定', '是/否各组可含多个出口；无匹配出口记录此思路失败。条件文本只展示，不执行。'],
          [
            '后继连线',
            node.outgoing
              .map(
                (edge) =>
                  `${edge.id}: ${edge.branch || '无是/否分组'} → ${edge.targetName} [${edge.target}]，顺序 ${edge.order}${edge.condition ? `，条件说明 ${edge.condition}` : ''}`,
              )
              .join('\n') || '无',
          ],
          [
            '定义位置',
            `workflow.json → nodes[${JSON.stringify(node.id)}]；参考文件见该节点 referenceImage 与 resources 清单`,
          ],
        ]
          .flatMap(([label, value]) => commentLines(label!, value!))
          .join('\n')
        return `\n\ndef node_${i + 1}(${args}):\n${details}\n    ${body}\n`
      })
      .join('')
    const mapping = selected.map((n, i) => `    ${JSON.stringify(n.id)}: node_${i + 1},`).join('\n')
    return `${template}${functions}\n\n# 节点 ID 是稳定关联键；重新生成到新目录后按此映射迁移业务实现。\nHANDLERS = {\n${mapping}\n}\n`
  }
  files['IMPLEMENTATION.md'] = `# Business implementation map / 业务实现索引

workflow.json is the shared definition. Node IDs, rather than function numbers, identify business logic.
workflow.json 为唯一主定义。按节点 ID 查找业务实现；node_N 只表示本次导出顺序。

runner.py → acquisition.py → parsing.py → display.py → diagnosis.py → routing.py → next node / 后继节点。
动作由 runner.py → actions.py → routing.py 调用。每个函数开头均有节点内容、输入输出和出口说明。
Only NotImplementedError requests manual fallback. Parsing/display defaults already work.
仅采集、判断和动作的未实现占位触发人工兜底；不是已绑定外部模块的真实执行。外部模块绑定由 Flowable worker 执行。
Offline handlers do not automatically import pythonModule/pythonFunction stored in workflow.json.
离线骨架不会自动导入定义中保存的 pythonModule/pythonFunction，请在下列函数里显式调用业务包。

${[
  ...investigations.map((node, i) => ({
    node,
    files: ['acquisition.py', 'parsing.py', 'display.py', 'diagnosis.py'].map(
      (name) => `${name}:node_${i + 1}`,
    ),
  })),
  ...actionNodes.map((node, i) => ({ node, files: [`actions.py:node_${i + 1}`] })),
]
  .map(
    ({ node, files }) =>
      `- ${JSON.stringify(node.name)} [${node.id}] (${node.kind}): ${files.join(', ')}`,
  )
  .join('\n')}

Keep IDs stable. Regenerate to a NEW directory and migrate your implementation by ID.
保持 ID 稳定；重新生成到新目录后按 ID 迁移实现，避免覆盖已有业务代码。
`
  files['acquisition.py'] = scaffold(
    'acquisition.py',
    acquisition,
    investigations,
    'node, context',
    'raise NotImplementedError("Implement automatic acquisition")',
  )
  files['parsing.py'] = scaffold(
    'parsing.py',
    parsing,
    investigations,
    'raw, node, context',
    'return raw',
  )
  files['display.py'] = scaffold(
    'display.py',
    display,
    investigations,
    'data, node, context',
    'default_display(data, node, context)',
  )
  files['diagnosis.py'] = scaffold(
    'diagnosis.py',
    diagnosis,
    investigations,
    'data, node, context',
    'raise NotImplementedError("Return True (yes) or False (no)")',
  )
  files['actions.py'] = scaffold(
    'actions.py',
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
- display.py: 展示解析数据，默认打印并通过本地浏览器打开参考文件（--no-images 关闭）。
- diagnosis.py: 自动诊断返回 True/False 或 yes/no；未实现时显示 assessment，人工决定下一步。
- routing.py: 校验是/否结果或人工选择，同分支按流程模式调度；条件文本仅展示，不执行、不推断。
- actions.py: 机台/处理动作；未实现时必须输入 yes 确认完成，否则停止。
- runner.py: 依赖调度、串行/并行排查、失败记录、成功暂停与恢复、子流程进入/返回、执行历史和循环步数限制。
- workflow.json / assets/: 通用诊断定义与实际资源，使用相对路径引用；没有重复的 BPMN 源图。

先查看 IMPLEMENTATION.md 的节点索引。每个函数上方提供节点 ID、类型、名称、业务内容、输入输出、调用关系和后继出口。
每个模块底部 HANDLERS 映射节点 ID 到 node_N 函数，在对应函数内填充逻辑。
See IMPLEMENTATION.md and each handler comment, then fill the functions linked by HANDLERS.
The offline scaffold does not automatically execute saved external-module bindings; those run through Flowable workers.
Only NotImplementedError triggers manual fallback; other exceptions stop execution.
仅 NotImplementedError 触发人工兜底，自动逻辑运行错误不会伪装成成功。

## 程序接口 / Python API

    from runner import run, Context
    result = run(supplied={"实际节点ID": {"voltage": 24}},
                 context=Context(open_images=False))

Context.ask / Context.show 可替换以连接自己的界面；Context.data 保存原始数据、解析结果和诊断结果。
Provide ask/show callbacks for another UI; context.data keeps raw/parsed data and results.
run 返回 status: problemSolved / escalation / jump / failed / paused。串行成功且有剩余思路时返回 state；
用 run(..., resume=result['state'], success_action='continue' 或 'finish') 继续或结束。
run returns diagnosticFailures and a resumable state on serial success; resume with an explicit continue/finish choice.
run 返回 status: problemSolved / escalation / jump，jump 表示需要转交其他链路，不表示问题已解决。
Jump is a handoff: no destination is currently stored in the editor; integrate external routing explicitly.

## 支持范围 / Scope

支持本项目诊断节点、普通开始事件、排他选择及嵌套普通子流程；子流程普通结束事件返回父流程。
并行模式下问题解决/上升结束当前路径，其他路径继续；串行按 diagnosisOrder 稳定升序执行，某思路失败后继续队列，成功后暂停等待继续/结束选择。没有匹配出口会记录失败，全部思路失败时返回 failed。
Parallel mode starts matching successors concurrently. Serial mode uses a persistent ordered queue and pauses on success while work remains. No matching outlet records a failed idea without restarting siblings.
条件表达式只供人工阅读；自动判断须在 diagnosis.py 返回 True/False 或 yes/no。默认流不自动猜测。
并行/包容网关、事件定义、多实例、普通任务、消息/跨流程连接等不支持时拒绝导出。
循环允许，但默认最多 1000 步（--max-steps）；自动函数自身的超时由实现者负责。
Supported: diagnostic nodes, plain starts, exclusive branches and nested plain subprocesses.
Unsupported BPMN constructs are rejected. Conditions are never evaluated as code.

重新导出到新目录，再迁移函数实现；不要覆盖已填写的业务代码。节点 ID 是数据与实现的关联键。
Regenerate into a NEW directory and migrate implementations; keep node IDs stable.
`
  return files
}
