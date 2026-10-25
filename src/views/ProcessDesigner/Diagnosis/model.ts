import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import type { Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import type { DiagnosisKind, DiagnosisBranch, InvestigationData } from '@/types/diagnosis'

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

export const diagnosisNodeName = (kind: DiagnosisKind, translate: (key: string) => string) => {
  if (kind === 'problemSolved') return '问题解决'
  if (kind === 'escalation') return '上升'
  return translate(diagnosisKinds[kind].label)
}

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
  if (!from && !to) return true
  if (getBusinessObject(source) === getBusinessObject(target)) return false
  if (from === 'problemSolved' || from === 'escalation') return false
  if (to === 'investigation' && from !== 'investigation' && from !== 'investigationAction') {
    return !from && is(source, 'bpmn:StartEvent')
  }
  if (to === 'investigationAction' && from !== 'investigation') return false
  if (from === 'investigationAction' && to !== 'investigation') return false
  if (to === 'conclusion' && from !== 'investigation') return false
  if (
    from === 'investigation' &&
    !['investigation', 'investigationAction', 'conclusion', 'jump', 'escalation'].includes(to || '')
  )
    return false
  if (from === 'conclusion' && !['remediation', 'jump', 'escalation'].includes(to || ''))
    return false
  if (
    (from === 'remediation' || from === 'jump') &&
    !['remediation', 'jump', 'problemSolved', 'deepDiagnosis', 'escalation'].includes(to || '')
  )
    return false
  return true
}

export const investigationFields: Record<keyof InvestigationData, string> = {
  observation: 'Specify the data to inspect',
  acquisition: 'Specify how to obtain the data',
  referenceImage: 'Add a reference image',
  assessment: 'Specify how to judge whether there is a problem',
}

export const isReferenceImage = (value: string) =>
  /^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/.test(value)

export const connectionError = 'Diagnostic connection violates diagnostic rules'

export const conclusionTextRequired = 'Conclusion requires a text description'
export const investigationActionTextRequired = 'Investigation action requires a text description'
export const conclusionSuccessorRequired =
  'Conclusion must have exactly one successor: a handling action or escalation'
export const fixedDiagnosisNameRequired = 'Final diagnosis node text is fixed'

export function getDiagnosisBranch(element: Element | ModdleElement): DiagnosisBranch | undefined {
  const bo = getBusinessObject(element)
  const branch = bo.get('flowable:diagnosisBranch')
  if (branch === 'yes' || branch === 'no') return branch
  const name = String(bo.get('name') || '')
    .trim()
    .toLowerCase()
  if (['yes', '是'].includes(name)) return 'yes'
  if (['no', '否'].includes(name)) return 'no'
}

export const summarizeConclusion = (text: string) => {
  const compact = text.trim().replace(/\s+/g, ' ')
  const characters = Array.from(compact)
  return characters.length > 30 ? characters.slice(0, 30).join('') + '…' : compact
}
