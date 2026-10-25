import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import originalRule from 'bpmnlint/rules/fake-join'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function fakeJoin(): RuleDefinition {
  const rule = originalRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void
  return {
    ...rule,
    check(node, reporter) {
      // 诊断汇合表示任一到达的路径继续，不要求等待其他处置措施。
      if (getDiagnosisKind(node)) return
      check(node, reporter)
    },
  }
}
