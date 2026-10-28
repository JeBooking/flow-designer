import type { RuleDefinition } from 'bpmnlint/lib/types'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import {
  connectionError,
  conclusionSuccessorRequired,
  getDiagnosisKind,
  getDiagnosisBranch,
  investigationFields,
  isDiagnosisConnectionAllowed,
  isReferenceFile,
} from '@/views/ProcessDesigner/Diagnosis/model'

export default function diagnosisRequired(): RuleDefinition {
  return {
    check(node, reporter) {
      const diagnosisKind = getDiagnosisKind(node)
      if (diagnosisKind === 'remediation' || diagnosisKind === 'investigationAction') {
        const module = String(node.get('flowable:pythonModule') || '').trim()
        const functionName = String(node.get('flowable:pythonFunction') || '').trim()
        const mode =
          node.get('flowable:actionMode') ||
          (node.get('flowable:pythonModule') || node.get('flowable:pythonFunction')
            ? 'automatic'
            : 'manual')
        if (!['automatic', 'manual', 'confirm'].includes(mode))
          reporter.report(node.id, 'Select a valid action execution mode')
        else if (mode !== 'manual' && (!module || !functionName))
          reporter.report(node.id, 'Action execution requires a Python project and interface')
      }
      if (diagnosisKind === 'investigation') {
        const flows: ModdleElement[] = node.get('outgoing') || []
        for (const flow of flows) {
          if (!getDiagnosisBranch(flow))
            reporter.report(flow.id, 'Select Yes or No for this branch')
        }
        for (const [field, message] of Object.entries(investigationFields)) {
          const value: unknown = node.get(`flowable:${field}`)
          if (
            typeof value !== 'string' ||
            !value.trim() ||
            (field === 'referenceImage' && !isReferenceFile(value))
          ) {
            reporter.report(node.id, message)
          }
        }
      }
      if (diagnosisKind === 'conclusion') {
        const outgoing: { targetRef?: ModdleElement }[] = node.get('outgoing') || []
        if (
          outgoing.length !== 1 ||
          outgoing.some((flow) => {
            const target = flow.targetRef
            const kind = target && getDiagnosisKind(target)
            return kind !== 'remediation' && kind !== 'jump' && kind !== 'escalation'
          })
        ) {
          reporter.report(node.id, conclusionSuccessorRequired)
        }
      }
      if (
        is(node, 'bpmn:SequenceFlow') ||
        is(node, 'bpmn:MessageFlow') ||
        is(node, 'bpmn:Association')
      ) {
        if (!isDiagnosisConnectionAllowed(node.sourceRef, node.targetRef)) {
          reporter.report(node.id, connectionError)
        }
      }
    },
  }
}
