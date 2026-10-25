import type { ModelElement } from '@/views/ProcessDesigner/CodeGeneration/generate'
import { diagnosisKinds, getDiagnosisBranch } from '@/views/ProcessDesigner/Diagnosis/model'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import { translateUi } from '@/languages/uiText'

interface DefinitionNode {
  kind: string
  [key: string]: unknown
}

/** 诊断定义只保存业务内容与执行语义；完整编辑状态仍由 BPMN 文件保存。 */
export function generateWorkflowDefinition(definitions: ModelElement): string {
  const list = (element: ModelElement, key: string) =>
    (element.get(key) as ModelElement[] | undefined) ?? []
  const processes = list(definitions, 'rootElements').filter(
    (root) => root.$type === 'bpmn:Process',
  )
  if (processes.length !== 1)
    throw new Error(translateUi('导出要求恰好一个流程。', 'Export requires exactly one process.'))
  const process = processes[0]!
  if (
    list(definitions, 'rootElements').some(
      (root) => root.$type === 'bpmn:Collaboration' && list(root, 'messageFlows').length,
    )
  )
    throw new Error(
      translateUi(
        '精简定义不支持跨流程消息流',
        'Compact definitions do not support cross-process message flows',
      ),
    )
  const nodes: Record<string, DefinitionNode> = Object.create(null)
  const builtins: Record<string, string> = {
    'bpmn:StartEvent': 'start',
    'bpmn:EndEvent': 'end',
    'bpmn:ExclusiveGateway': 'gateway',
    'bpmn:SubProcess': 'subprocess',
  }
  const fields = [
    'observation',
    'acquisition',
    'assessment',
    'referenceImage',
    'pythonModule',
    'pythonFunction',
    'pythonArguments',
    'pythonTopic',
  ] as const
  const readScope = (scope: ModelElement): string => {
    const elements = list(scope, 'flowElements')
    const starts = elements.filter((element) => element.$type === 'bpmn:StartEvent')
    if (starts.length !== 1)
      throw new Error(
        translateUi('需要且只能有一个开始事件', 'Exactly one start event is required') +
          ': ' +
          scope.id,
      )
    for (const element of elements) {
      if (element.$type === 'bpmn:SequenceFlow') continue
      const kind = String(element.get('flowable:diagnosisKind') || '')
      const diagnostic =
        element.$type === 'bpmn:Task' && Object.prototype.hasOwnProperty.call(diagnosisKinds, kind)
      const builtin = builtins[element.$type]
      if (
        (!diagnostic && !builtin) ||
        list(element, 'eventDefinitions').length ||
        element.get('loopCharacteristics') ||
        element.get('triggeredByEvent') ||
        element.get('isForCompensation')
      )
        throw new Error(
          translateUi(
            '精简定义不支持此元素：',
            'Compact definitions do not support this element: ',
          ) + element.id,
        )
      const node: DefinitionNode = { kind: diagnostic ? kind : builtin! }
      if (scope !== process) node.scope = scope.id
      const nameMode = diagnostic ? element.get('flowable:nameMode') : undefined
      // 自动摘要随节点尺寸变化，属于显示结果，精简定义只保留原始详情与自动命名策略。
      if (element.get('name') && nameMode !== 'auto') node.name = element.get('name')
      const documentation = list(element, 'documentation')
        .map((item) => String(item.get('text') || ''))
        .join('\n')
      if (documentation) node.documentation = documentation
      if (diagnostic) {
        for (const field of fields) {
          const value = element.get('flowable:' + field)
          if (value !== undefined && value !== '') node[field] = value
        }
        const detail =
          element.get('flowable:detailText') ??
          element.get(kind === 'conclusion' ? 'flowable:conclusionText' : 'flowable:actionText')
        if (detail) node.detailText = detail
        if (nameMode === 'auto') node.nameMode = 'auto'
        if (element.get('flowable:humanDecision')) node.humanDecision = true
      }
      const outgoing = elements
        .filter(
          (flow) =>
            flow.$type === 'bpmn:SequenceFlow' &&
            (flow.get('sourceRef') as ModelElement | undefined)?.id === element.id,
        )
        .map((flow) => {
          const edge: Record<string, unknown> = {
            id: flow.id,
            target: (flow.get('targetRef') as ModelElement | undefined)?.id,
          }
          if (!edge.target)
            throw new Error(translateUi('连线缺少终点：', 'Missing connection target: ') + flow.id)
          const branch = getDiagnosisBranch(flow as ModdleElement)
          if (branch) edge.branch = branch
          const name = flow.get('name')
          if (name && name !== branch) edge.name = name
          const order = flow.get('flowable:diagnosisOrder')
          if (order !== undefined) edge.order = order
          const condition = flow.get('conditionExpression') as ModelElement | undefined
          if (condition?.get('body')) edge.condition = condition.get('body')
          if ((element.get('default') as ModelElement | undefined)?.id === flow.id)
            edge.default = true
          return edge
        })
      if (outgoing.length) node.outgoing = outgoing
      if (builtin === 'subprocess') node.start = readScope(element)
      nodes[element.id] = node
    }
    return starts[0]!.id
  }
  const start = readScope(process)
  const metadata: Record<string, unknown> = { id: process.id }
  if (process.get('name')) metadata.name = process.get('name')
  const documentation = list(process, 'documentation')
    .map((item) => String(item.get('text') || ''))
    .join('\n')
  if (documentation) metadata.documentation = documentation
  return JSON.stringify(
    {
      version: 3,
      process: metadata,
      mode: process.get('flowable:diagnosisMode') || 'parallel',
      start,
      nodes,
    },
    null,
    2,
  )
}
