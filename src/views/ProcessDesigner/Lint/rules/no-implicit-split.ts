import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import originalRule from 'bpmnlint/rules/no-implicit-split'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function noImplicitSplit(): RuleDefinition {
  const rule = originalRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void
  return {
    ...rule,
    check(node, reporter) {
      // 已绑定接口的诊断分支由导出器插入排他网关，Python 返回后继连线 ID。
      if (
        getDiagnosisKind(node) &&
        node.get('flowable:pythonModule') &&
        node.get('flowable:pythonFunction')
      )
        return
      check(node, reporter)
    },
  }
}
