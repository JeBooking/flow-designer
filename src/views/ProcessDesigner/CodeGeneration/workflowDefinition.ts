import type { ModelElement } from '@/views/ProcessDesigner/CodeGeneration/generate'
import { diagnosisKinds, getDiagnosisBranch } from '@/views/ProcessDesigner/Diagnosis/model'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import { translateUi } from '@/languages/uiText'
import type { ProjectFiles } from '@/views/ProcessDesigner/CodeGeneration/generate'
import {
  decodeResource,
  resourceExtension,
  resourcePath,
} from '@/views/ProcessDesigner/CodeGeneration/resources'
import type { WorkflowResource } from '@/views/ProcessDesigner/CodeGeneration/resources'
import {
  getDiagnosisDetail,
  isLegacyAutomaticName,
} from '@/views/ProcessDesigner/Diagnosis/geometry'
import type { DiagnosisKind } from '@/types/diagnosis'

interface DefinitionNode {
  kind: string
  [key: string]: unknown
}

/** 诊断定义只保存业务内容与执行语义；完整编辑状态仍由 BPMN 文件保存。 */
export function generateWorkflowDefinition(definitions: ModelElement): string {
  return generateWorkflowProject(definitions)['workflow.json'] as string
}

export function generateWorkflowProject(definitions: ModelElement): ProjectFiles {
  const files: ProjectFiles = {}
  const resources: WorkflowResource[] = []
  const saved = new Map<string, string>()
  const saveResource = (value: string, originalPath?: string, filename?: string) => {
    const existing = saved.get(value)
    if (existing) return existing
    const decoded = decodeResource(value)
    const safeName = filename?.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/[. ]+$/, '')
    const suggested = safeName ? `assets/${safeName}` : undefined
    let path = decoded
      ? originalPath
        ? resourcePath(originalPath)
        : suggested ||
          `assets/resource_${resources.length + 1}.${resourceExtension(decoded.mediaType)}`
      : resourcePath(value)
    if (decoded && !originalPath) {
      let index = resources.length + 1
      while (resources.some((entry) => entry.path === path)) {
        const suffix = ++index
        path = suggested
          ? suggested.replace(/(\.[^./]+)?$/, `_${suffix}$1`)
          : `assets/resource_${suffix}.${resourceExtension(decoded.mediaType)}`
      }
    }
    if (decoded) files[path] = decoded.data
    const entry = resources.find((resource) => resource.path === path)
    if (entry && decoded?.mediaType) entry.mediaType = decoded.mediaType
    else if (!entry)
      resources.push({ path, ...(decoded?.mediaType ? { mediaType: decoded.mediaType } : {}) })
    saved.set(value, path)
    return path
  }
  const list = (element: ModelElement, key: string) =>
    (element.get(key) as ModelElement[] | undefined) ?? []
  const processes = list(definitions, 'rootElements').filter(
    (root) => root.$type === 'bpmn:Process',
  )
  if (processes.length !== 1)
    throw new Error(translateUi('导出要求恰好一个流程。', 'Export requires exactly one process.'))
  const process = processes[0]!
  const storedResources = process.get('flowable:resourceManifest')
  if (typeof storedResources === 'string' && storedResources) {
    const entries: unknown = JSON.parse(storedResources)
    if (!Array.isArray(entries))
      throw new Error(translateUi('资源清单无效', 'Invalid resource manifest'))
    for (const entry of entries) {
      if (
        !entry ||
        typeof entry.path !== 'string' ||
        (entry.mediaType !== undefined && typeof entry.mediaType !== 'string')
      )
        throw new Error(translateUi('资源清单无效', 'Invalid resource manifest'))
      const path = resourcePath(entry.path)
      if (!saved.has(path)) {
        resources.push({ path, ...(entry.mediaType ? { mediaType: entry.mediaType } : {}) })
        saved.set(path, path)
      }
    }
  }
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
    'referenceImageName',
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
      const storedMode = diagnostic ? element.get('flowable:nameMode') : undefined
      const detail = diagnostic ? getDiagnosisDetail(element as ModdleElement) : ''
      const nameMode =
        storedMode ||
        (diagnostic &&
        isLegacyAutomaticName(kind as DiagnosisKind, String(element.get('name') || ''), detail) &&
        (element.get('name') || detail)
          ? 'auto'
          : undefined)
      // 自动摘要随节点尺寸变化，属于显示结果，精简定义只保留原始详情与自动命名策略。
      if (element.get('name') && nameMode !== 'auto') node.name = element.get('name')
      const documentation = list(element, 'documentation')
        .map((item) => String(item.get('text') || ''))
        .join('\n')
      if (documentation) node.documentation = documentation
      if (diagnostic) {
        for (const field of fields) {
          const value = element.get('flowable:' + field)
          if (
            field === 'referenceImageName' &&
            value ===
              String(node.referenceImage || '')
                .split('/')
                .slice(-1)[0]
          )
            continue
          if (value !== undefined && value !== '')
            node[field] =
              field === 'referenceImage'
                ? saveResource(
                    String(value),
                    element.get('flowable:referenceImagePath') as string | undefined,
                    element.get('flowable:referenceImageName') as string | undefined,
                  )
                : value
        }
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
  files['workflow.json'] = JSON.stringify(
    {
      version: 4,
      process: metadata,
      mode: process.get('flowable:diagnosisMode') || 'parallel',
      start,
      nodes,
      ...(resources.length ? { resources } : {}),
    },
    null,
    2,
  )
  return files
}
