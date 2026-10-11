import type { RuleDefinition } from 'bpmnlint/lib/types'
import type { ModdleElement } from 'bpmnlint/lib/types'
import { is, isAny } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function endEventRequired(): RuleDefinition {
  return {
    check(node, reporter) {
      if (!isAny(node, ['bpmn:Process', 'bpmn:SubProcess']) || is(node, 'bpmn:AdHocSubProcess')) {
        return
      }

      const flowElements = node.get('flowElements') || []
      const hasEnd = flowElements.some((element: ModdleElement) => {
        const kind = getDiagnosisKind(element)
        return is(element, 'bpmn:EndEvent') || kind === 'problemSolved' || kind === 'escalation'
      })

      if (!hasEnd) {
        const type = is(node, 'bpmn:SubProcess') ? 'Sub process' : 'Process'
        reporter.report(node.id, `${type} is missing end event`)
      }
    },
  }
}
