import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type Modeling from 'bpmn-js/lib/features/modeling/Modeling'
import type { Shape } from 'bpmn-js/lib/model/Types'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind, summarizeConclusion } from '@/views/ProcessDesigner/Diagnosis/model'
import {
  automaticDiagnosisName,
  getDiagnosisDetail,
} from '@/views/ProcessDesigner/Diagnosis/geometry'

export default class DiagnosisBehavior extends CommandInterceptor {
  static $inject = ['eventBus', 'modeling']

  constructor(eventBus: EventBus, modeling: Modeling) {
    super(eventBus)
    // 补齐原命令的字段，名称、旧字段和新详情只占用一次撤销记录。
    this.preExecute(
      ['element.updateProperties', 'element.updateModdleProperties'],
      ({ context }) => {
        const { element, properties } = context
        const kind = getDiagnosisKind(element)
        if (!kind) return
        const bo = getBusinessObject(element)
        if (context.moddleElement && context.moddleElement !== bo) return
        const oldDetail = getDiagnosisDetail(element)
        const legacyKey =
          kind === 'conclusion'
            ? 'flowable:conclusionText'
            : kind === 'investigationAction'
              ? 'flowable:actionText'
              : undefined
        const detailChanged =
          'flowable:detailText' in properties || !!(legacyKey && legacyKey in properties)
        if (detailChanged) {
          const detail = String(
            properties['flowable:detailText'] ?? (legacyKey ? properties[legacyKey] : '') ?? '',
          )
          properties['flowable:detailText'] = detail
          if (legacyKey) properties[legacyKey] = detail
          const oldName = String(bo.get('name') || '')
          const mode = bo.get('flowable:nameMode')
          // 无模式的旧图保留手填名称；旧版自动结论摘要仍可继续自动更新。
          const automatic =
            mode === 'auto' ||
            (!mode &&
              (!oldName.trim() ||
                (kind === 'conclusion' && oldName === summarizeConclusion(oldDetail))))
          if (!('name' in properties) && automatic) {
            properties.name = automaticDiagnosisName(element, detail)
            properties['flowable:nameMode'] = 'auto'
          }
        }
        if ('name' in properties && !('flowable:nameMode' in properties)) {
          const name = String(properties.name || '')
          properties['flowable:nameMode'] = name.trim() ? 'manual' : 'auto'
          if (!name.trim())
            properties.name = automaticDiagnosisName(
              element,
              String(properties['flowable:detailText'] ?? oldDetail),
            )
          else if (kind === 'conclusion' && (!oldDetail.trim() || oldDetail === bo.get('name'))) {
            properties['flowable:detailText'] = name
            properties['flowable:conclusionText'] = name
          }
        }
      },
    )
    // 画布内双击编辑直接执行 updateLabel，不经过属性更新命令。
    this.postExecuted('element.updateLabel', ({ context }) => {
      const shape = (context.element.labelTarget || context.element) as Shape
      const kind = getDiagnosisKind(shape)
      if (!kind) return
      const name = String(getBusinessObject(shape).get('name') || '')
      const detail = getDiagnosisDetail(shape)
      const properties: Record<string, string> = {
        name: name.trim() ? name : automaticDiagnosisName(shape),
        'flowable:nameMode': name.trim() ? 'manual' : 'auto',
      }
      if (kind === 'conclusion' && name.trim() && (!detail.trim() || detail === context.oldLabel)) {
        properties['flowable:detailText'] = name
        properties['flowable:conclusionText'] = name
      }
      modeling.updateProperties(shape, properties)
    })
    this.postExecuted(['shape.create', 'shape.resize'], ({ context }) => {
      const shape = context.shape as Shape
      if (!shape || !getDiagnosisKind(shape) || shape.labelTarget) return
      const bo = getBusinessObject(shape)
      if (bo.get('flowable:nameMode') === 'auto' || !bo.get('name')) {
        const name = automaticDiagnosisName(shape)
        if (name !== (bo.get('name') || ''))
          modeling.updateProperties(shape, { name, 'flowable:nameMode': 'auto' })
      }
    })
  }
}
