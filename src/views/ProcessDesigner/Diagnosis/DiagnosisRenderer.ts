import BaseRenderer from 'diagram-js/lib/draw/BaseRenderer'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type BpmnRenderer from 'bpmn-js/lib/draw/BpmnRenderer'
import type { Shape } from 'bpmn-js/lib/model/Types'
import { append, attr, create } from 'tiny-svg'
import { diagnosisKinds, getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export default class DiagnosisRenderer extends BaseRenderer {
  static $inject = ['eventBus', 'bpmnRenderer']

  constructor(
    eventBus: EventBus,
    private bpmnRenderer: BpmnRenderer,
  ) {
    super(eventBus, 1800)
  }

  canRender(element: Shape) {
    return !element.labelTarget && !!getDiagnosisKind(element)
  }

  drawShape(parent: SVGElement, element: Shape) {
    const shape = this.bpmnRenderer.drawShape(parent, element)
    const kind = getDiagnosisKind(element)!
    attr(shape, { stroke: diagnosisKinds[kind].color, 'stroke-width': 2 })
    const marker = create('text')
    attr(marker, {
      x: 10,
      y: 19,
      fill: diagnosisKinds[kind].color,
      'font-size': 17,
      'font-weight': 'bold',
      'pointer-events': 'none',
    })
    marker.textContent = {
      investigation: '?',
      investigationAction: '⚙',
      conclusion: '=',
      remediation: '✓',
      deepDiagnosis: '↻',
      jump: '↗',
      problemSolved: '✓',
      escalation: '↑',
    }[kind]
    append(parent, marker)
    return shape
  }

  getShapePath(shape: Shape) {
    return this.bpmnRenderer.getShapePath(shape)
  }
}
