import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import type { Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import type { DiagnosisKind, InvestigationData } from '@/types/diagnosis'

export const diagnosisKinds: Record<DiagnosisKind, { label: string; icon: string; color: string }> =
  {
    investigation: { label: 'Investigation', icon: 'bpmn-icon-service-task', color: '#2563eb' },
    conclusion: { label: 'Conclusion', icon: 'bpmn-icon-user-task', color: '#7c3aed' },
    remediation: { label: 'Remediation', icon: 'bpmn-icon-manual-task', color: '#059669' },
    escalation: { label: 'Escalation', icon: 'bpmn-icon-send-task', color: '#d97706' },
  }

export function getDiagnosisKind(element?: Element | ModdleElement): DiagnosisKind | undefined {
  if (!element || !is(element, 'bpmn:Task')) return
  const kind: string | undefined = getBusinessObject(element).get('flowable:diagnosisKind')
  if (kind && Object.prototype.hasOwnProperty.call(diagnosisKinds, kind))
    return kind as DiagnosisKind
}

// 仅拒绝诊断业务禁止的连接，其余情况继续交给 BPMN 规则检查作用域及连线类型。
export function isDiagnosisConnectionAllowed(
  source?: Element | ModdleElement,
  target?: Element | ModdleElement,
): boolean {
  if (!source || !target) return true
  const from = getDiagnosisKind(source)
  const to = getDiagnosisKind(target)
  if (from !== 'investigation' && to !== 'investigation') return true
  if (getBusinessObject(source) === getBusinessObject(target)) return false
  if (
    to === 'investigation' &&
    from !== 'investigation' &&
    from !== 'conclusion' &&
    !is(source, 'bpmn:StartEvent')
  ) {
    return false
  }
  if (
    from === 'investigation' &&
    !['investigation', 'conclusion', 'remediation', 'escalation'].includes(to || '')
  ) {
    return false
  }
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

export const connectionError =
  'Investigation requires a start event, investigation or conclusion predecessor and an investigation, conclusion, remediation or escalation successor'
