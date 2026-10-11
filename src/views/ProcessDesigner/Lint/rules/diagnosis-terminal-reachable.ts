import type { ModdleElement, RuleDefinition } from 'bpmnlint/lib/types'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default function diagnosisTerminalReachable(): RuleDefinition {
  return {
    check(scope, reporter) {
      if (!is(scope, 'bpmn:Process') && !is(scope, 'bpmn:SubProcess')) return
      if (is(scope, 'bpmn:AdHocSubProcess')) return

      const flowElements: ModdleElement[] = scope.get('flowElements') || []
      const flowNodes = flowElements.filter((element) => is(element, 'bpmn:FlowNode'))
      const diagnosisNodes = flowNodes.filter((element) => !!getDiagnosisKind(element))
      if (!diagnosisNodes.length) return

      const predecessors = new Map<ModdleElement, Set<ModdleElement>>()
      const successors = new Map<ModdleElement, Set<ModdleElement>>()
      for (const flowNode of flowNodes) {
        predecessors.set(flowNode, new Set())
        successors.set(flowNode, new Set())
      }
      for (const flow of flowElements.filter((element) => is(element, 'bpmn:SequenceFlow'))) {
        const source = flow.get('sourceRef') as ModdleElement | undefined
        const target = flow.get('targetRef') as ModdleElement | undefined
        if (!source || !target || !successors.has(source) || !predecessors.has(target)) continue
        successors.get(source)?.add(target)
        predecessors.get(target)?.add(source)
      }

      // 只校验与诊断节点相连的流程片段，避免影响同一模型中的其他流程。
      const component = new Set<ModdleElement>()
      const componentQueue = [...diagnosisNodes]
      while (componentQueue.length) {
        const current = componentQueue.shift()!
        if (component.has(current)) continue
        component.add(current)
        for (const neighbor of [
          ...(predecessors.get(current) || []),
          ...(successors.get(current) || []),
        ]) {
          if (!component.has(neighbor)) componentQueue.push(neighbor)
        }
      }

      const terminalKinds = new Set(['problemSolved', 'escalation', 'jump'])
      const reachesTerminal = new Set(
        [...component].filter((element) => terminalKinds.has(getDiagnosisKind(element) || '')),
      )
      const terminalQueue = [...reachesTerminal]
      while (terminalQueue.length) {
        const current = terminalQueue.shift()!
        for (const predecessor of predecessors.get(current) || []) {
          if (component.has(predecessor) && !reachesTerminal.has(predecessor)) {
            reachesTerminal.add(predecessor)
            terminalQueue.push(predecessor)
          }
        }
      }

      const unreachable = new Set([...component].filter((element) => !reachesTerminal.has(element)))
      while (unreachable.size) {
        const first = unreachable.values().next().value as ModdleElement
        const failedComponent = new Set<ModdleElement>()
        const failedQueue = [first]
        while (failedQueue.length) {
          const current = failedQueue.shift()!
          if (failedComponent.has(current)) continue
          failedComponent.add(current)
          for (const neighbor of [
            ...(predecessors.get(current) || []),
            ...(successors.get(current) || []),
          ]) {
            if (unreachable.has(neighbor) && !failedComponent.has(neighbor)) {
              failedQueue.push(neighbor)
            }
          }
        }
        for (const element of failedComponent) unreachable.delete(element)

        // 每个失败分支只在其末端节点提示；纯闭环没有末端时选一个节点代表该闭环。
        const failedEnds = [...failedComponent].filter(
          (element) =>
            ![...(successors.get(element) || [])].some((successor) =>
              failedComponent.has(successor),
            ),
        )
        const markers = failedEnds.length ? failedEnds : [failedComponent.values().next().value!]
        for (const element of markers) {
          reporter.report(
            element.id,
            'Every diagnostic branch must reach Problem Solved or Escalation, or end at Jump',
          )
        }
      }
    },
  }
}
