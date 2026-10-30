import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import type { Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import type { DiagnosisKind, DiagnosisBranch, InvestigationData } from '@/types/diagnosis'
import connectionRules from '@/rules/diagnosis-connections.json'

export const diagnosisKinds: Record<DiagnosisKind, { label: string; icon: string; color: string }> =
  {
    investigation: { label: 'Investigation', icon: 'bpmn-icon-service-task', color: '#2563eb' },
    investigationAction: {
      label: 'Investigation Action',
      icon: 'bpmn-icon-manual-task',
      color: '#0891b2',
    },
    conclusion: { label: 'Conclusion', icon: 'bpmn-icon-user-task', color: '#7c3aed' },
    remediation: { label: 'Remediation', icon: 'bpmn-icon-manual-task', color: '#059669' },
    deepDiagnosis: { label: 'Deep Diagnosis', icon: 'bpmn-icon-service-task', color: '#4f46e5' },
    jump: { label: 'Jump', icon: 'bpmn-icon-call-activity', color: '#64748b' },
    problemSolved: { label: 'Problem Solved', icon: 'bpmn-icon-task', color: '#16a34a' },
    escalation: { label: 'Escalation', icon: 'bpmn-icon-send-task', color: '#d97706' },
  }

export const diagnosisNodeName = () => ''

export function getDiagnosisKind(element?: Element | ModdleElement): DiagnosisKind | undefined {
  if (!element || !is(element, 'bpmn:Task')) return
  const kind: string | undefined = getBusinessObject(element).get('flowable:diagnosisKind')
  if (kind && Object.prototype.hasOwnProperty.call(diagnosisKinds, kind))
    return kind as DiagnosisKind
}

export const isFixedDiagnosisNode = (element?: Element | ModdleElement) => {
  const kind = getDiagnosisKind(element)
  return kind === 'problemSolved' || kind === 'escalation'
}

// 仅拒绝诊断业务禁止的连接，其余情况继续交给 BPMN 规则检查作用域及连线类型。
export function isDiagnosisConnectionAllowed(
  source?: Element | ModdleElement,
  target?: Element | ModdleElement,
): boolean {
  if (!source || !target) return true
  const from = getDiagnosisKind(source)
  const to = getDiagnosisKind(target)
  // 普通 BPMN 子流程等仍交给原生规则；诊断节点与普通节点的边界也由共享表约束。
  const sourceKind = from || (is(source, 'bpmn:StartEvent') ? 'start' : 'generic')
  const targetKind = to || (is(target, 'bpmn:StartEvent') ? 'start' : 'generic')
  if (sourceKind === 'generic' && targetKind === 'generic') return true
  if (getBusinessObject(source) === getBusinessObject(target)) return false
  const targets: readonly string[] = connectionRules[sourceKind]
  return targets.includes(targetKind)
}

export const investigationFields: Record<
  Exclude<keyof InvestigationData, 'referenceImageName'>,
  string
> = {
  observation: 'Specify the data to inspect',
  acquisition: 'Specify how to obtain the data',
  referenceImage: 'Add a reference file',
  assessment: 'Specify how to judge whether there is a problem',
}

export const MAX_REFERENCE_FILE_BYTES = 50 * 1024 * 1024

// 内部画布允许临时 data URI；导出器必须把内容拆成独立资源文件。
export const parseReferenceFile = (value: string) => {
  const match =
    /^data:([A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+);base64,([A-Za-z0-9+/]*={0,2})$/.exec(
      value,
    )
  if (!match) return
  const base64 = match[2]!
  if (base64.length % 4 !== 0) return
  const size = (base64.length / 4) * 3 - (base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0)
  if (size > MAX_REFERENCE_FILE_BYTES) return
  try {
    if (btoa(atob(base64)) !== base64) return
  } catch {
    return
  }
  return { mediaType: match[1]!.toLowerCase(), base64 }
}

export const isReferenceFile = (value: string) => Boolean(parseReferenceFile(value))
// 保留旧调用方名称，避免已有流程和编译入口失效。
export const isReferenceImage = isReferenceFile

export const connectionError = 'Diagnostic connection violates diagnostic rules'

export const conclusionTextRequired = 'Conclusion requires a text description'
export const investigationActionTextRequired = 'Investigation action requires a text description'
export const conclusionSuccessorRequired =
  'Conclusion must have exactly one successor: a handling action or escalation'
export const fixedDiagnosisNameRequired = 'Final diagnosis node text is fixed'

export function parseDiagnosisBranch(value: unknown): DiagnosisBranch | undefined {
  if (typeof value !== 'string') return
  const normalized = value.trim().toLowerCase()
  if (normalized === 'yes' || normalized === '是') return 'yes'
  if (normalized === 'no' || normalized === '否') return 'no'
}

export function getDiagnosisBranch(element: Element | ModdleElement): DiagnosisBranch | undefined {
  const bo = getBusinessObject(element)
  if (!is(bo, 'bpmn:SequenceFlow') || getDiagnosisKind(bo.get('sourceRef')) !== 'investigation')
    return
  return (
    parseDiagnosisBranch(bo.get('flowable:diagnosisBranch')) || parseDiagnosisBranch(bo.get('name'))
  )
}

export const summarizeConclusion = (text: string) => {
  const compact = text.trim().replace(/\s+/g, ' ')
  const characters = Array.from(compact)
  return characters.length > 30 ? characters.slice(0, 30).join('') + '…' : compact
}
