import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const dependencyRoot = process.env.DIAGNOSIS_DEPENDENCIES || process.cwd()
const require = createRequire(path.join(dependencyRoot, 'package.json'))
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const BpmnModdle = createRequire(require.resolve('bpmn-js/package.json'))('bpmn-moddle')
const temp = await mkdtemp(path.join(tmpdir(), 'diagnosis-names-'))
try {
  await build({
    stdin: {
      contents: `
        export { default as EventBus } from 'diagram-js/lib/core/EventBus'
        export { default as CommandStack } from 'diagram-js/lib/command/CommandStack'
        export { default as UpdatePropertiesHandler } from 'bpmn-js/lib/features/modeling/cmd/UpdatePropertiesHandler'
        export { default as UpdateModdlePropertiesHandler } from 'bpmn-js/lib/features/modeling/cmd/UpdateModdlePropertiesHandler'
        export { default as UpdateLabelHandler } from 'bpmn-js/lib/features/label-editing/cmd/UpdateLabelHandler'
        export { default as LabelBehavior } from 'bpmn-js/lib/features/modeling/behavior/LabelBehavior'
        export { default as DiagnosisBehavior } from '@/views/ProcessDesigner/Diagnosis/DiagnosisBehavior'
        export { automaticDiagnosisName, getDiagnosisDetail, isLegacyAutomaticName } from '@/views/ProcessDesigner/Diagnosis/geometry'
      `,
      resolveDir: process.cwd(),
    },
    outfile: path.join(temp, 'names.mjs'),
    bundle: true,
    platform: 'node',
    format: 'esm',
    nodePaths: [path.join(dependencyRoot, 'node_modules')],
    alias: { '@': path.join(process.cwd(), 'src') },
  })
  const {
    EventBus,
    CommandStack,
    UpdateModdlePropertiesHandler,
    UpdatePropertiesHandler,
    UpdateLabelHandler,
    LabelBehavior,
    DiagnosisBehavior,
    automaticDiagnosisName,
    getDiagnosisDetail,
    isLegacyAutomaticName,
  } = await import(pathToFileURL(path.join(temp, 'names.mjs')))
  const descriptor = JSON.parse(await readFile('src/views/ProcessDesigner/flowable.json', 'utf8'))
  const moddle = new BpmnModdle({ flowable: descriptor })
  const eventBus = new EventBus()
  const stack = new CommandStack(eventBus, {})
  const modeling = {
    updateProperties(element, properties) {
      stack.execute('element.updateModdleProperties', {
        element,
        moddleElement: element.businessObject,
        properties,
      })
    },
    updateLabel(element, newLabel) {
      stack.execute('element.updateLabel', { element, newLabel })
    },
  }
  stack.register('element.updateProperties', new UpdatePropertiesHandler({}, moddle, modeling, {}))
  stack.register('element.updateModdleProperties', new UpdateModdlePropertiesHandler({}))
  stack.register('element.updateLabel', new UpdateLabelHandler(modeling, {}, {}))
  stack.register('shape.resize', {
    execute(context) {
      context.oldBounds = { width: context.shape.width, height: context.shape.height }
      Object.assign(context.shape, context.newBounds)
      return [context.shape]
    },
    revert(context) {
      Object.assign(context.shape, context.oldBounds)
      return [context.shape]
    },
  })
  new LabelBehavior(eventBus, modeling, {}, {})
  new DiagnosisBehavior(eventBus, modeling)
  for (const kind of ['investigationAction', 'conclusion', 'remediation']) {
    const bo = moddle.create('bpmn:Task', {
      id: kind,
      'flowable:diagnosisKind': kind,
      'flowable:nameMode': 'auto',
    })
    const shape = { id: kind, type: 'bpmn:Task', businessObject: bo, width: 100, height: 80 }
    const update = (properties) => modeling.updateProperties(shape, properties)
    const detail = '检查设备连接状态，重新连接设备并等待指示灯恢复正常。'.repeat(5)
    assert.equal(bo.get('name') || '', '')
    update({ 'flowable:detailText': detail })
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    assert.equal(bo.get('flowable:nameMode'), 'auto')
    stack.undo()
    assert.equal(bo.get('flowable:detailText'), undefined)
    assert.equal(bo.get('name'), undefined)
    stack.redo()
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    const narrowName = bo.get('name')
    stack.execute('shape.resize', { shape, newBounds: { width: 220, height: 140 } })
    assert.notEqual(bo.get('name'), narrowName)
    stack.undo()
    assert.equal(bo.get('name'), narrowName)
    stack.redo()
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    update({ name: '手填名称' })
    update({ 'flowable:detailText': '新的详细内容' })
    assert.equal(bo.get('name'), '手填名称')
    update({ name: '' })
    assert.equal(bo.get('name'), '新的详细内容')
    assert.equal(bo.get('flowable:nameMode'), 'auto')
    modeling.updateLabel(shape, '画布手填名称')
    update({ 'flowable:detailText': '又一次修改内容' })
    assert.equal(bo.get('name'), '画布手填名称')
    modeling.updateLabel(shape, '')
    assert.equal(bo.get('name'), '又一次修改内容')
    assert.equal(bo.get('flowable:nameMode'), 'auto')
    stack.execute('element.updateProperties', {
      shape,
      element: shape,
      properties: { 'flowable:detailText': '通过普通属性命令更新' },
    })
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    stack.undo()
    assert.equal(bo.get('flowable:detailText'), '又一次修改内容')
    stack.redo()
    const { xml } = await moddle.toXML(bo)
    assert.match(xml, /flowable:nameMode="auto"/)
    assert.ok(!xml.includes('camunda:'))
    const restored = await moddle.fromXML(xml, 'bpmn:Task')
    assert.equal(restored.rootElement.get('name'), bo.get('name'))
    assert.equal(restored.rootElement.get('flowable:detailText'), bo.get('flowable:detailText'))
    stack.clear()
  }
  for (const oldName of ['排查动作', 'Investigation Action']) {
    const bo = moddle.create('bpmn:Task', {
      id: 'LegacyAction',
      name: oldName,
      'flowable:diagnosisKind': 'investigationAction',
      'flowable:detailText': '',
      'flowable:actionText': '旧动作详情',
    })
    const shape = {
      id: 'LegacyAction',
      type: 'bpmn:Task',
      businessObject: bo,
      width: 100,
      height: 80,
    }
    assert.equal(getDiagnosisDetail(shape), '旧动作详情')
    assert.equal(isLegacyAutomaticName('investigationAction', oldName, '旧动作详情'), true)
    modeling.updateProperties(shape, { 'flowable:detailText': '更新后的动作详情' })
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    assert.equal(bo.get('flowable:nameMode'), 'auto')
    stack.undo()
    assert.equal(bo.get('name'), oldName)
    assert.equal(bo.get('flowable:nameMode'), undefined)
    stack.redo()
    assert.equal(bo.get('name'), automaticDiagnosisName(shape))
    modeling.updateProperties(shape, { name: oldName, 'flowable:nameMode': 'manual' })
    modeling.updateProperties(shape, { 'flowable:detailText': '保持手填类型名' })
    assert.equal(bo.get('name'), oldName)
    modeling.updateProperties(shape, { 'flowable:detailText': '' })
    assert.equal(getDiagnosisDetail(shape), '')
    stack.clear()
  }
  assert.equal(isLegacyAutomaticName('investigationAction', '设备复位', '详情'), false)
  console.log('Diagnosis name command-stack verification passed')
} finally {
  await rm(temp, { recursive: true, force: true })
}
