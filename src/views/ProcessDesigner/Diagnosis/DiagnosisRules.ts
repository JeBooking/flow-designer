import RuleProvider from 'diagram-js/lib/features/rules/RuleProvider'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type { Connection, Element, Shape } from 'bpmn-js/lib/model/Types'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import {
  getDiagnosisKind,
  isDiagnosisConnectionAllowed,
} from '@/views/ProcessDesigner/Diagnosis/model'

export default class DiagnosisRules extends RuleProvider {
  static $inject = ['eventBus']

  constructor(eventBus: EventBus) {
    super(eventBus)
  }

  init() {
    this.addRule(
      ['connection.create', 'connection.reconnect'],
      2000,
      (context: { source?: Element; target?: Element; connection?: Connection }) => {
        const source = context.source || context.connection?.source
        const target = context.target || context.connection?.target
        if (!isDiagnosisConnectionAllowed(source, target)) return false
      },
    )
    this.addRule('shape.create', 2000, (context: { source?: Shape; shape: Shape }) => {
      if (!isDiagnosisConnectionAllowed(context.source, context.shape)) return false
    })
    this.addRule(
      ['elements.create', 'elements.move'],
      2000,
      (context: { elements?: Element[]; shapes?: Shape[]; target?: Element }) => {
        const elements = context.elements || context.shapes || []
        for (const element of elements) {
          if (
            is(element, 'bpmn:SequenceFlow') &&
            !isDiagnosisConnectionAllowed(element.source, element.target)
          )
            return false
        }
        // 插入连线会自动拆成两条边，必须同时检查两侧，避免绕过画线规则。
        if (context.target && is(context.target, 'bpmn:SequenceFlow')) {
          const connection = context.target as Connection
          const shapes = elements.filter((element) => is(element, 'bpmn:FlowNode'))
          if (
            shapes.some(
              (shape) =>
                !isDiagnosisConnectionAllowed(connection.source, shape) ||
                !isDiagnosisConnectionAllowed(shape, connection.target),
            )
          )
            return false
        }
      },
    )
    this.addRule('shape.replace', 2000, (context: { element?: Shape; oldShape?: Shape }) => {
      if (getDiagnosisKind(context.element || context.oldShape)) return false
    })
  }
}
