import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import originalRule from 'bpmnlint/rules/no-implicit-split'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function noImplicitSplit(): RuleDefinition {
  const rule = originalRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void
  return {
    ...rule,
    check(node, reporter) {
      // 自动和人工分支都由导出器插入排他网关，避免误报隐式并行。
      if (
        getDiagnosisKind(node) &&
        (node.get('flowable:humanDecision') ||
          (node.get('flowable:pythonModule') && node.get('flowable:pythonFunction')))
      )
        return
      check(node, reporter)
    },
  }
}
