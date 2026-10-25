import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor'
import type CommandStack from 'diagram-js/lib/command/CommandStack'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type Modeling from 'bpmn-js/lib/features/modeling/Modeling'
import type { Connection, Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import { translateUi } from '@/languages/uiText'
import {
  getDiagnosisBranch,
  getDiagnosisKind,
  parseDiagnosisBranch,
} from '@/views/ProcessDesigner/Diagnosis/model'

interface BranchEditContext {
  element?: Element
  moddleElement?: ModdleElement
  properties?: Record<string, unknown>
  newLabel?: string
}

function getBranchConnection(element?: Element): Element | undefined {
  const target = element?.labelTarget || element
  if (
    target &&
    is(target, 'bpmn:SequenceFlow') &&
    getDiagnosisKind(getBusinessObject(target).get('sourceRef')) === 'investigation'
  )
    return target
}

export default class DiagnosisBranchBehavior extends CommandInterceptor {
  static $inject = ['eventBus', 'modeling', 'commandStack']

  constructor(eventBus: EventBus, modeling: Modeling, commandStack: CommandStack) {
    super(eventBus)

    // preExecute 无法取消命令；在入口校验，避免非法输入占用撤销记录或破坏 redo。
    const execute = commandStack.execute.bind(commandStack)
    commandStack.execute = (command, context) => {
      const edit = context as BranchEditContext
      const connection = getBranchConnection(edit.element)
      const bo = connection && getBusinessObject(connection)
      const properties = edit.properties
      let invalid = false
      if (connection && (!edit.moddleElement || edit.moddleElement === bo)) {
        if (command === 'element.updateLabel') invalid = !parseDiagnosisBranch(edit.newLabel)
        else if (
          properties &&
          ['element.updateProperties', 'element.updateModdleProperties'].includes(command)
        ) {
          if ('name' in properties) invalid = !parseDiagnosisBranch(properties.name)
          if ('flowable:diagnosisBranch' in properties)
            invalid ||= !parseDiagnosisBranch(properties['flowable:diagnosisBranch'])
        }
      }
      if (invalid) {
        ElMessage.warning(
          translateUi(
            '判断分支仅支持“是”、“否”、“yes”或“no”（英文不区分大小写）。',
            'Decision branches only accept 是, 否, yes, or no (case-insensitive).',
          ),
        )
        eventBus.fire('elements.changed', { elements: [connection] })
        return
      }
      execute(command, context)
    }

    this.preExecute(
      ['element.updateProperties', 'element.updateModdleProperties'],
      ({ context }) => {
        const connection = getBranchConnection(context.element)
        if (!connection) return
        if (context.moddleElement && context.moddleElement !== getBusinessObject(connection)) return
        const properties = context.properties as Record<string, unknown>
        const branch =
          'name' in properties
            ? parseDiagnosisBranch(properties.name)
            : parseDiagnosisBranch(properties['flowable:diagnosisBranch'])
        if (!branch) return
        properties.name = branch
        properties['flowable:diagnosisBranch'] = branch
        properties.conditionExpression = undefined
      },
    )

    this.preExecute('element.updateLabel', ({ context }) => {
      const connection = getBranchConnection(context.element)
      const branch = parseDiagnosisBranch(context.newLabel)
      if (!connection || !branch) return
      context.newLabel = branch
      const bo = getBusinessObject(connection)
      // bpmn-js 属性变更会再次调用 updateLabel，分类已同步时不再嵌套写入。
      if (bo.get('flowable:diagnosisBranch') === branch && !bo.get('conditionExpression')) return
      // 与标签命令组成同一撤销单元，属性和显示文本始终一起恢复。
      modeling.updateProperties(connection, {
        'flowable:diagnosisBranch': branch,
        name: branch,
        conditionExpression: undefined,
      })
    })

    this.postExecuted(['connection.create', 'connection.reconnect'], ({ context }) => {
      const connection = context.connection as Connection
      if (getBranchConnection(connection)) {
        const branch = getDiagnosisBranch(connection) || 'yes'
        modeling.updateProperties(connection, {
          'flowable:diagnosisBranch': branch,
          name: branch,
          conditionExpression: undefined,
        })
      } else if (getBusinessObject(connection).get('flowable:diagnosisBranch') !== undefined) {
        // 离开排查出口后删除业务分类，普通 BPMN 连线继续使用原有条件语义。
        modeling.updateProperties(connection, { 'flowable:diagnosisBranch': undefined })
      }
    })
  }
}
