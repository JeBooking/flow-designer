import type { RuleDefinition } from 'bpmnlint/lib/types'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import {
  connectionError,
  getDiagnosisKind,
  investigationFields,
  isDiagnosisConnectionAllowed,
  isReferenceImage,
} from '@/views/ProcessDesigner/Diagnosis/model'

export default function diagnosisRequired(): RuleDefinition {
  return {
    check(node, reporter) {
      if (getDiagnosisKind(node) === 'investigation') {
        for (const [field, message] of Object.entries(investigationFields)) {
          const value: unknown = node.get(`flowable:${field}`)
          if (
            typeof value !== 'string' ||
            !value.trim() ||
            (field === 'referenceImage' && !isReferenceImage(value))
          ) {
            reporter.report(node.id, message)
          }
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
