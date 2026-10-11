import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import noImplicitEndRule from 'bpmnlint/rules/no-implicit-end'
import { getDiagnosisKind, isFixedDiagnosisNode } from '@/views/ProcessDesigner/Diagnosis/model'

export default function noImplicitEnd(): RuleDefinition {
  const rule = noImplicitEndRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void

  return {
    ...rule,
    check(node, reporter) {
      if (isFixedDiagnosisNode(node) || getDiagnosisKind(node) === 'jump') return
      check(node, reporter)
    },
  }
}
