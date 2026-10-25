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
import {
  diagnosisPath,
  diagnosisTextBox,
  labelLines,
} from '@/views/ProcessDesigner/Diagnosis/geometry'

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
    const kind = getDiagnosisKind(element)!
    const shape =
      kind === 'deepDiagnosis' ? this.bpmnRenderer.drawShape(parent, element) : create('path')
    if (kind !== 'deepDiagnosis') {
      attr(shape, { d: diagnosisPath(element), fill: 'var(--bpmn-fill-color, white)' })
      append(parent, shape)
    }
    parent.querySelectorAll('.djs-label').forEach((label) => label.remove())
    if (kind === 'deepDiagnosis') {
      const marker = create('text')
      attr(marker, {
        x: 10,
        y: 19,
        fill: diagnosisKinds[kind].color,
        'font-size': 17,
        'pointer-events': 'none',
      })
      marker.textContent = '↻'
      append(parent, marker)
    }
    attr(shape, { stroke: diagnosisKinds[kind].color, 'stroke-width': 2 })
    const text = String(getBusinessObject(element).get('name') || '')
    const box = diagnosisTextBox(element.width, element.height, kind)
    const lines = labelLines(text, box.width)
    const label = create('text')
    // 手填长名称不改变节点大小，按可用内接矩形缩放字号。
    const lineHeight = Math.min(16, box.height / Math.max(1, lines.length))
    attr(label, {
      class: 'djs-label',
      'font-family': 'Arial, sans-serif',
      'font-size': Math.min(12, lineHeight / 1.3),
      'text-anchor': 'middle',
      fill: 'currentColor',
      'pointer-events': 'none',
    })
    lines.forEach((line, index) => {
      const span = create('tspan')
      attr(span, {
        x: element.width / 2,
        y: box.centerY + (index - (lines.length - 1) / 2) * lineHeight,
        'dominant-baseline': 'middle',
      })
      span.textContent = line
      append(label, span)
    })
    append(parent, label)
    return shape
  }

  getShapePath(shape: Shape) {
    return getDiagnosisKind(shape) && getDiagnosisKind(shape) !== 'deepDiagnosis'
      ? diagnosisPath(shape, true)
      : this.bpmnRenderer.getShapePath(shape)
  }
}
