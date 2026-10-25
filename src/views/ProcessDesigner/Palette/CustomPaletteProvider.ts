import PaletteProvider, { type Translate } from 'bpmn-js/lib/features/palette/PaletteProvider'
import Palette from 'diagram-js/lib/features/palette/Palette'
import Create from 'diagram-js/lib/features/create/Create'
import ElementFactory from 'bpmn-js/lib/features/modeling/ElementFactory'
import SpaceTool from 'diagram-js/lib/features/space-tool/SpaceTool'
import LassoTool from 'diagram-js/lib/features/lasso-tool/LassoTool'
import HandTool from 'diagram-js/lib/features/hand-tool/HandTool'
import GlobalConnect from 'diagram-js/lib/features/global-connect/GlobalConnect'
import type { PaletteEntries } from 'diagram-js/lib/features/palette/PaletteProvider'
import { diagnosisKinds, diagnosisNodeName } from '@/views/ProcessDesigner/Diagnosis/model'
import type { DiagnosisKind } from '@/types/diagnosis'
import { createElement } from '@/views/ProcessDesigner/utils/ElementUtil'
import type BpmnFactory from 'bpmn-js/lib/features/modeling/BpmnFactory'

export default class CustomPaletteProvider extends PaletteProvider {
  static $inject = [
    'palette',
    'create',
    'elementFactory',
    'spaceTool',
    'lassoTool',
    'handTool',
    'globalConnect',
    'translate',
    'bpmnFactory',
  ]
  private elementFactory: ElementFactory
  private create: Create
  private readonly translate: Translate

  constructor(
    palette: Palette,
    create: Create,
    elementFactory: ElementFactory,
    spaceTool: SpaceTool,
    lassoTool: LassoTool,
    handTool: HandTool,
    globalConnect: GlobalConnect,
    translate: Translate,
    private bpmnFactory: BpmnFactory,
  ) {
    super(palette, create, elementFactory, spaceTool, lassoTool, handTool, globalConnect, translate)
    this.elementFactory = elementFactory
    this.create = create
    this.translate = translate
  }

  getPaletteEntries() {
    const actions: PaletteEntries = super.getPaletteEntries()
    for (const [kind, definition] of Object.entries(diagnosisKinds) as [
      DiagnosisKind,
      (typeof diagnosisKinds)[DiagnosisKind],
    ][]) {
      const createDiagnosis = (event: Event) => {
        const businessObject = createElement('bpmn:Task', this.bpmnFactory, {
          'flowable:diagnosisKind': kind,
          name: diagnosisNodeName(),
          'flowable:nameMode': 'auto',
        })
        this.create.start(
          event,
          this.elementFactory.createShape({ type: 'bpmn:Task', businessObject }),
        )
      }
      actions[`create.diagnosis-${kind}`] = {
        group: 'diagnosis',
        className: definition.icon,
        title: this.translate(`Create ${definition.label}`),
        action: { click: createDiagnosis, dragstart: createDiagnosis },
      }
    }
    for (const key of Object.keys(actions)) {
      if (
        key.startsWith('create.') &&
        key !== 'create.subprocess-expanded' &&
        !key.startsWith('create.diagnosis-')
      ) {
        delete actions[key]
      }
    }
    return actions
  }
}
