import type { ModdleElement, Reporter, RuleDefinition } from 'bpmnlint/lib/types'
import originalRule from 'bpmnlint/rules/fake-join'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function fakeJoin(): RuleDefinition {
  const rule = originalRule()
  const check = rule.check as (node: ModdleElement, reporter: Reporter) => void
  return {
    ...rule,
    check(node, reporter) {
      const scope = node.$parent
      const elements: ModdleElement[] = scope?.get('flowElements') || []
      // 已绑定的纯诊断图由导出器执行排他路由，汇合表示继续当前支路，不等待并行支路。
      const exclusiveDiagnosis =
        elements.length > 0 &&
        elements.every((element) => {
          if (is(element, 'bpmn:SequenceFlow') || is(element, 'bpmn:StartEvent')) return true
          const kind = getDiagnosisKind(element)
          return (
            kind &&
            (['problemSolved', 'escalation'].includes(kind) ||
              element.get('flowable:humanDecision') ||
              (element.get('flowable:pythonModule') && element.get('flowable:pythonFunction')))
          )
        })
      if (getDiagnosisKind(node) && exclusiveDiagnosis) return
      check(node, reporter)
    },
  }
}
