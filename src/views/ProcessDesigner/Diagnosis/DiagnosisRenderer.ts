import BaseRenderer from 'diagram-js/lib/draw/BaseRenderer'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type BpmnRenderer from 'bpmn-js/lib/draw/BpmnRenderer'
import type { Shape } from 'bpmn-js/lib/model/Types'
import { append, attr, create } from 'tiny-svg'
import {
  diagnosisKinds,
  getDiagnosisKind,
  getDiagnosisBranch,
} from '@/views/ProcessDesigner/Diagnosis/model'
import { translateUi } from '@/languages/uiText'
import type TextRenderer from 'bpmn-js/lib/draw/TextRenderer'
import type ElementRegistry from 'diagram-js/lib/core/ElementRegistry'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { labelLines } from '@/views/ProcessDesigner/Diagnosis/DiagnosisBehavior'

export default class DiagnosisRenderer extends BaseRenderer {
  static $inject = ['eventBus', 'bpmnRenderer', 'textRenderer', 'elementRegistry']

  constructor(
    eventBus: EventBus,
    private bpmnRenderer: BpmnRenderer,
    private textRenderer: TextRenderer,
    elementRegistry: ElementRegistry,
  ) {
    super(eventBus, 1800)
    eventBus.on('i18n.changed', () =>
      eventBus.fire('elements.changed', {
        elements: elementRegistry.filter(
          (element) => !!element.labelTarget && !!getDiagnosisBranch(element),
        ),
      }),
    )
  }

  canRender(element: Shape) {
    return element.labelTarget ? !!getDiagnosisBranch(element) : !!getDiagnosisKind(element)
  }

  drawShape(parent: SVGElement, element: Shape) {
    if (element.labelTarget) {
      const label = create('text')
      const style = this.textRenderer.getExternalStyle()
      // 翻译后的 Yes 比模型中的 yes 稍宽，保持单行以免沿用旧标签宽度造成断字。
      attr(label, {
        class: 'djs-label',
        x: element.width / 2,
        y: element.height / 2,
        'text-anchor': 'middle',
        'dominant-baseline': 'middle',
        'font-family': style.fontFamily,
        'font-size': style.fontSize,
        fill: 'currentColor',
      })
      label.textContent =
        getDiagnosisBranch(element) === 'yes' ? translateUi('是', 'Yes') : translateUi('否', 'No')
      append(parent, label)
      return label
    }
    const shape = this.bpmnRenderer.drawShape(parent, element)
    parent.querySelector('.djs-label')?.remove()
    const text = String(getBusinessObject(element).get('name') || '')
    const lines = labelLines(text, element.width)
    const label = create('text')
    attr(label, {
      class: 'djs-label',
      'font-family': 'Arial, sans-serif',
      'font-size': 12,
      'text-anchor': 'middle',
      fill: 'currentColor',
    })
    // 老图的尺寸可能偏小，渲染时缩小字号保证内容仍位于节点内；编辑后命令栈会扩容。
    const lineHeight = Math.min(18, Math.max(1, (element.height - 30) / lines.length))
    attr(label, { 'font-size': Math.min(12, lineHeight / 1.5) })
    lines.forEach((line, index) => {
      const span = create('tspan')
      attr(span, { x: element.width / 2, y: 25 + lineHeight * (index + 0.8) })
      span.textContent = line
      append(label, span)
    })
    append(parent, label)
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
