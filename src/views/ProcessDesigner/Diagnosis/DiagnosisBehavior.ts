import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type Modeling from 'bpmn-js/lib/features/modeling/Modeling'
import type { Shape } from 'bpmn-js/lib/model/Types'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'
import {
  automaticDiagnosisName,
  getDiagnosisDetail,
  isLegacyAutomaticName,
} from '@/views/ProcessDesigner/Diagnosis/geometry'

export default class DiagnosisBehavior extends CommandInterceptor {
  static $inject = ['eventBus', 'modeling']

  constructor(eventBus: EventBus, modeling: Modeling) {
    super(eventBus)
    const propertyUpdates = new Set<{ element: Shape }>()
    // 补齐原命令的字段，名称、旧字段和新详情只占用一次撤销记录。
    this.preExecute(
      ['element.updateProperties', 'element.updateModdleProperties'],
      ({ context }) => {
        const { element, properties } = context
        const kind = getDiagnosisKind(element)
        if (!kind) return
        const bo = getBusinessObject(element)
        if (context.moddleElement && context.moddleElement !== bo) return
        propertyUpdates.add(context)
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
          // 无模式旧图的类型占位名应继续自动生成，显式手填名称不能被详情覆盖。
          const automatic =
            mode === 'auto' || (!mode && isLegacyAutomaticName(kind, oldName, oldDetail))
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
    this.postExecuted(
      ['element.updateProperties', 'element.updateModdleProperties'],
      ({ context }) => {
        propertyUpdates.delete(context)
      },
    )
    // 属性更新的 LabelBehavior 会嵌套调用 updateLabel；只处理真正的画布名称编辑。
    // 否则自动摘要会被误标为手填，并再次触发属性更新造成递归。
    // 画布内双击编辑直接执行 updateLabel，不经过属性更新命令。
    this.postExecuted('element.updateLabel', ({ context }) => {
      const shape = (context.element.labelTarget || context.element) as Shape
      const kind = getDiagnosisKind(shape)
      if (!kind || [...propertyUpdates].some((update) => update.element === shape)) return
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
