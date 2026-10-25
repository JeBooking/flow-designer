import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import originalRule from 'bpmnlint/rules/no-implicit-split'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function noImplicitSplit(): RuleDefinition {
  const rule = originalRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void
  return {
    ...rule,
    check(node, reporter) {
      // 诊断分支由导出器显式转换为条件并行或普通并行。
      if (getDiagnosisKind(node)) return
      check(node, reporter)
    },
  }
}
