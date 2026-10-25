import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type Modeling from 'bpmn-js/lib/features/modeling/Modeling'
import type { Shape, Connection } from 'bpmn-js/lib/model/Types'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import {
  getDiagnosisKind,
  getDiagnosisBranch,
  summarizeConclusion,
} from '@/views/ProcessDesigner/Diagnosis/model'

export function labelLines(text: string, width: number): string[] {
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')!
  context.font = '12px Arial, sans-serif'
  return text.split('\n').flatMap((paragraph) => {
    const lines: string[] = []
    let line = ''
    for (const character of paragraph) {
      if (line && context.measureText(line + character).width > Math.max(24, width - 24)) {
        lines.push(line)
        line = ''
      }
      line += character
    }
    return [...lines, line]
  })
}

export default class DiagnosisBehavior extends CommandInterceptor {
  static $inject = ['eventBus', 'modeling']

  constructor(eventBus: EventBus, modeling: Modeling) {
    super(eventBus)
    // 在原命令中补全成对字段，撤销一次即可同时恢复名称和内容。
    this.preExecute(
      ['element.updateProperties', 'element.updateModdleProperties'],
      ({ context }) => {
        const { element, properties } = context
        if (getDiagnosisKind(element) !== 'conclusion') return
        const bo = getBusinessObject(element)
        if (context.moddleElement && context.moddleElement !== bo) return
        const oldName = bo.get('name') || ''
        const oldText = bo.get('flowable:conclusionText') || ''
        if ('flowable:conclusionText' in properties) {
          const text = properties['flowable:conclusionText'] || ''
          if (!text.trim() && oldName.trim()) properties['flowable:conclusionText'] = oldName
          else if (
            !oldName.trim() ||
            ['结论', '结论节点', 'Conclusion'].includes(oldName) ||
            oldName === summarizeConclusion(oldText)
          )
            properties.name = summarizeConclusion(text)
        } else if ('name' in properties) {
          if (!properties.name?.trim() && oldText.trim())
            properties.name = summarizeConclusion(oldText)
          else if (!oldText.trim() || oldText === oldName)
            properties['flowable:conclusionText'] = properties.name
        }
      },
    )
    this.postExecuted('element.updateLabel', ({ context }) => {
      const element = context.element as Shape
      if (getDiagnosisKind(element) !== 'conclusion') return
      const bo = getBusinessObject(element)
      const text = bo.get('flowable:conclusionText') || ''
      const name = bo.get('name') || ''
      if (!name.trim() && text.trim())
        modeling.updateProperties(element, { name: summarizeConclusion(text) })
      else if (name.trim() && name !== text && (!text.trim() || text === context.oldLabel))
        modeling.updateProperties(element, { 'flowable:conclusionText': name })
    })
    this.postExecuted(['connection.create', 'connection.reconnect'], ({ context }) => {
      const connection = context.connection as Connection
      if (
        !connection.source ||
        getDiagnosisKind(connection.source) !== 'investigation' ||
        getDiagnosisBranch(connection)
      )
        return
      const others = connection.source.outgoing.filter((flow) => flow !== connection)
      const branch = others.some((flow) => getDiagnosisBranch(flow) === 'yes') ? 'no' : 'yes'
      modeling.updateProperties(connection, { 'flowable:diagnosisBranch': branch, name: branch })
    })
    this.postExecuted(['shape.create', 'element.updateLabel', 'shape.resize'], ({ context }) => {
      const shape = (context.shape || context.element) as Shape
      if (!shape || !getDiagnosisKind(shape) || shape.labelTarget) return
      const text = String(getBusinessObject(shape).get('name') || '')
      const preferredWidth = Math.min(
        320,
        Array.from(text).reduce((width, char) => width + (/[^\x00-\x7F]/.test(char) ? 12 : 7), 24),
      )
      const width = Math.max(120, shape.width, context.newBounds ? 0 : preferredWidth)
      const height = Math.max(80, shape.height, labelLines(text, width).length * 18 + 36)
      if (width !== shape.width || height !== shape.height)
        modeling.resizeShape(shape, { x: shape.x, y: shape.y, width, height })
    })
  }
}
