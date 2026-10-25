import { layoutProcess } from 'bpmn-auto-layout'
import { translateUi } from '@/languages/uiText'
import { diagnosisKinds, parseDiagnosisBranch } from '@/views/ProcessDesigner/Diagnosis/model'

interface WorkflowEdge {
  id: string
  name?: string
  target: string
  branch?: string
  order?: number
  condition?: string
  default?: boolean
}

interface WorkflowNode {
  id: string
  kind: string
  scope: string
  name?: string
  start?: string
  outgoing: WorkflowEdge[]
  observation?: string
  acquisition?: string
  assessment?: string
  referenceImage?: string
  detailText?: string
  actionText?: string
  conclusionText?: string
  documentation?: string
}

const record = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value)
const hasOwn = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key)
const escapeXml = (value: string) =>
  value.replace(/[<>&"'\r\n\t]/g, (character) => {
    const entities: Record<string, string> = {
      '<': '&lt;',
      '>': '&gt;',
      '&': '&amp;',
      '"': '&quot;',
      "'": '&apos;',
      '\r': '&#13;',
      '\n': '&#10;',
      '\t': '&#9;',
    }
    return entities[character]!
  })
const attribute = (key: string, value?: string | number) =>
  value === undefined ? '' : ` ${key}="${escapeXml(String(value))}"`

/** 先完整校验、生成和布局，成功后调用方才替换画布，损坏文件不会清空原图。 */
export async function importWorkflowJson(content: string): Promise<{
  xml: string
  missingImages: number
  unclassifiedBranches: number
}> {
  const fail = (detail: string): never => {
    throw new Error(
      translateUi('无法恢复 workflow.json：', 'Unable to restore workflow.json: ') + detail,
    )
  }
  let data: unknown
  try {
    data = JSON.parse(content.replace(/^\uFEFF/, ''))
  } catch {
    return fail(translateUi('JSON 格式错误', 'Invalid JSON'))
  }
  if (!record(data) || !record(data.nodes) || typeof data.start !== 'string')
    return fail(translateUi('缺少 nodes 或 start', 'Missing nodes or start'))
  if (data.version !== undefined && data.version !== 1 && data.version !== 2)
    return fail(translateUi('不支持的文件版本', 'Unsupported file version'))
  if (data.mode !== undefined && data.mode !== 'parallel' && data.mode !== 'serial')
    return fail(translateUi('无效排查模式', 'Invalid investigation mode'))
  const nodes = new Map<string, WorkflowNode>()
  const ids = new Set<string>()
  const id = (value: unknown) => {
    if (
      typeof value !== 'string' ||
      !/^[\p{L}_][\p{L}\p{N}\p{M}_.-]*$/u.test(value) ||
      ids.has(value)
    )
      return fail(translateUi('元素 ID 无效或重复', 'Invalid or duplicate element ID'))
    ids.add(value)
    return value
  }
  const builtins: Record<string, string> = {
    start: 'startEvent',
    end: 'endEvent',
    gateway: 'exclusiveGateway',
    subprocess: 'subProcess',
  }
  const fields = [
    'name',
    'start',
    'observation',
    'acquisition',
    'assessment',
    'referenceImage',
    'detailText',
    'actionText',
    'conclusionText',
    'documentation',
  ] as const
  for (const [key, value] of Object.entries(data.nodes)) {
    if (
      !record(value) ||
      value.id !== key ||
      typeof value.scope !== 'string' ||
      typeof value.kind !== 'string' ||
      !Array.isArray(value.outgoing)
    )
      return fail(translateUi('节点结构不完整：', 'Incomplete node: ') + key)
    id(key)
    if (!hasOwn(builtins, value.kind) && !hasOwn(diagnosisKinds, value.kind))
      return fail(translateUi('不支持的节点类型：', 'Unsupported node kind: ') + value.kind)
    for (const field of fields)
      if (value[field] !== undefined && typeof value[field] !== 'string')
        return fail(key + ': ' + field)
    for (const edge of value.outgoing) {
      if (
        !record(edge) ||
        typeof edge.target !== 'string' ||
        (edge.name !== undefined && typeof edge.name !== 'string') ||
        (edge.branch !== undefined && typeof edge.branch !== 'string') ||
        (edge.condition !== undefined && typeof edge.condition !== 'string') ||
        (edge.order !== undefined && !Number.isSafeInteger(edge.order)) ||
        (edge.default !== undefined && typeof edge.default !== 'boolean')
      )
        return fail(translateUi('连线结构无效：', 'Invalid connection: ') + key)
      id(edge.id)
    }
    // 外部 JSON 已在上方逐字段验证，后续仅操作新建模型，不修改现有业务对象。
    nodes.set(key, value as unknown as WorkflowNode)
  }
  const start = nodes.get(data.start)
  if (!start || start.kind !== 'start')
    return fail(translateUi('开始节点不存在', 'Start node is missing'))
  const processId = id(start.scope)
  for (const node of nodes.values()) {
    const scopes = new Set([node.id])
    let scope = node.scope
    while (scope !== processId) {
      const parent = nodes.get(scope)
      if (!parent || parent.kind !== 'subprocess' || scopes.has(scope))
        return fail(translateUi('子流程归属无效：', 'Invalid subprocess scope: ') + node.id)
      scopes.add(scope)
      scope = parent.scope
    }
    if (node.kind === 'subprocess') {
      const child = node.start && nodes.get(node.start)
      if (!child || child.kind !== 'start' || child.scope !== node.id)
        return fail(translateUi('子流程缺少开始节点：', 'Subprocess start is missing: ') + node.id)
    }
    for (const edge of node.outgoing) {
      const target = nodes.get(edge.target)
      if (!target || target.scope !== node.scope)
        return fail(
          translateUi('连线端点不存在或跨越子流程：', 'Missing or cross-scope endpoint: ') +
            edge.id,
        )
    }
  }
  let missingImages = 0
  let unclassifiedBranches = 0
  const scopeXml = (scope: string): string => {
    const children = [...nodes.values()].filter((node) => node.scope === scope)
    const nodeXml = children
      .map((node) => {
        const tag = builtins[node.kind] || 'task'
        const diagnostic = !hasOwn(builtins, node.kind)
        let attributes = attribute('id', node.id) + attribute('name', node.name)
        const defaults = node.outgoing.filter((edge) => edge.default)
        if (defaults.length > 1)
          return fail(node.id + ': ' + translateUi('存在多个默认出口', 'Multiple default flows'))
        if (defaults[0]) attributes += attribute('default', defaults[0].id)
        if (node.kind === 'subprocess') attributes += ' triggeredByEvent="false"'
        if (diagnostic) {
          attributes += attribute('flowable:diagnosisKind', node.kind)
          // JSON 中没有名称来源标记；现有名称作为手填保留，避免详情修改意外覆盖。
          if (node.name) attributes += attribute('flowable:nameMode', 'manual')
          for (const field of fields.filter(
            (field) => !['name', 'start', 'documentation'].includes(field),
          )) {
            const value = node[field]
            if (field === 'referenceImage' && value && !value.startsWith('data:image/'))
              missingImages++
            attributes += attribute('flowable:' + field, value)
          }
        }
        const documentation = node.documentation
          ? `<bpmn:documentation>${escapeXml(node.documentation)}</bpmn:documentation>`
          : ''
        const incoming = children
          .flatMap((source) => source.outgoing)
          .filter((edge) => edge.target === node.id)
          .map((edge) => `<bpmn:incoming>${escapeXml(edge.id)}</bpmn:incoming>`)
          .join('')
        const outgoing = node.outgoing
          .map((edge) => `<bpmn:outgoing>${escapeXml(edge.id)}</bpmn:outgoing>`)
          .join('')
        return `<bpmn:${tag}${attributes}>${documentation}${incoming}${outgoing}${node.kind === 'subprocess' ? scopeXml(node.id) : ''}</bpmn:${tag}>`
      })
      .join('')
    const flowXml = children
      .flatMap((node) =>
        node.outgoing.map((edge) => {
          let attributes =
            attribute('id', edge.id) +
            attribute('sourceRef', node.id) +
            attribute('targetRef', edge.target)
          const branch =
            node.kind === 'investigation'
              ? parseDiagnosisBranch(edge.branch || edge.name)
              : undefined
          // 旧版任意分支名称保留原拓扑，提示用户补充分组，不猜测是或否。
          if (node.kind === 'investigation' && !branch) unclassifiedBranches++
          attributes += attribute('name', branch || edge.name)
          attributes +=
            attribute('flowable:diagnosisBranch', branch) +
            attribute('flowable:diagnosisOrder', edge.order)
          const condition = edge.condition
            ? `<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">${escapeXml(edge.condition)}</bpmn:conditionExpression>`
            : ''
          return `<bpmn:sequenceFlow${attributes}>${condition}</bpmn:sequenceFlow>`
        }),
      )
      .join('')
    return nodeXml + flowXml
  }
  let definitionId = 'Restored_Definitions'
  while (ids.has(definitionId)) definitionId += '_'
  const xml = `<?xml version="1.0" encoding="UTF-8"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:flowable="http://flowable.org/bpmn" id="${definitionId}" targetNamespace="http://bpmn.io/schema/bpmn"><bpmn:process${attribute('id', processId)} isExecutable="true"${attribute('flowable:diagnosisMode', String(data.mode || 'parallel'))}>${scopeXml(processId)}</bpmn:process></bpmn:definitions>`
  return { xml: await layoutProcess(xml), missingImages, unclassifiedBranches }
}
