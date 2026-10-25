// 用真实 Moddle 和布局库验证旧 JSON 恢复；不启动浏览器或修改现有流程。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const require = createRequire(import.meta.url)
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const BpmnModdle = createRequire(require.resolve('bpmn-js/package.json'))('bpmn-moddle')
const temp = await mkdtemp(path.join(tmpdir(), 'workflow-import-'))
try {
  const entry = path.join(temp, 'import.mjs')
  await build({
    entryPoints: ['src/views/ProcessDesigner/CodeGeneration/importWorkflow.ts'],
    outfile: entry,
    bundle: true,
    platform: 'node',
    format: 'esm',
    alias: { '@': path.join(process.cwd(), 'src') },
  })
  const { importWorkflowJson } = await import(pathToFileURL(entry))
  const descriptor = JSON.parse(await readFile('src/views/ProcessDesigner/flowable.json', 'utf8'))
  const moddle = new BpmnModdle({ flowable: descriptor })
  const workflow = {
    version: 2,
    mode: 'serial',
    start: 'Start',
    nodes: {
      Start: {
        id: 'Start',
        kind: 'start',
        scope: 'Process',
        outgoing: [{ id: 'Begin', target: 'Inspect' }],
      },
      Inspect: {
        id: 'Inspect',
        kind: 'investigation',
        scope: 'Process',
        name: '检查 <设备> & "电压"',
        detailText: '第一行\n第二行',
        observation: '曲线',
        acquisition: '采集',
        assessment: '判断',
        referenceImage: 'images/reference_1.png',
        outgoing: [
          { id: 'Yes1', target: 'Conclusion', branch: 'YES', order: 2 },
          { id: 'Yes2', target: 'Failed', branch: 'yes', order: 1 },
          { id: 'No', target: 'Solved', branch: '否' },
        ],
      },
      Failed: { id: 'Failed', kind: 'investigation', scope: 'Process', outgoing: [] },
      Conclusion: {
        id: 'Conclusion',
        kind: 'conclusion',
        scope: 'Process',
        conclusionText: '设备异常',
        documentation: '记录 <原文>',
        outgoing: [{ id: 'Fix', target: 'Repair' }],
      },
      Repair: {
        id: 'Repair',
        kind: 'remediation',
        scope: 'Process',
        detailText: '重新连接',
        outgoing: [{ id: 'Finish', target: 'Solved' }],
      },
      Solved: { id: 'Solved', kind: 'problemSolved', scope: 'Process', outgoing: [] },
    },
  }
  const result = await importWorkflowJson('\uFEFF' + JSON.stringify(workflow))
  assert.equal(result.missingImages, 1)
  const { rootElement, warnings } = await moddle.fromXML(result.xml)
  assert.equal(warnings.length, 0)
  const restoredProcess = rootElement.rootElements[0]
  assert.equal(restoredProcess.get('flowable:diagnosisMode'), 'serial')
  const elements = new Map(restoredProcess.flowElements.map((element) => [element.id, element]))
  assert.equal(elements.get('Inspect').name, workflow.nodes.Inspect.name)
  assert.equal(elements.get('Inspect').get('flowable:detailText'), '第一行\n第二行')
  assert.equal(elements.get('Conclusion').documentation[0].text, '记录 <原文>')
  assert.equal(elements.get('Yes1').get('flowable:diagnosisBranch'), 'yes')
  assert.equal(elements.get('Yes1').get('flowable:diagnosisOrder'), 2)
  assert.equal(elements.get('Yes2').targetRef, elements.get('Failed'))
  assert.equal(elements.get('No').get('flowable:diagnosisBranch'), 'no')
  assert.equal(elements.get('Inspect').outgoing.length, 3)
  assert.ok(rootElement.diagrams[0].plane.planeElement.length >= 12)
  const legacy = structuredClone(workflow)
  delete legacy.version
  delete legacy.mode
  legacy.nodes.Inspect.outgoing.forEach((edge) => {
    edge.name = edge.branch
    delete edge.branch
  })
  const restored = await moddle.fromXML((await importWorkflowJson(JSON.stringify(legacy))).xml)
  assert.equal(restored.rootElement.rootElements[0].get('flowable:diagnosisMode'), 'parallel')
  legacy.nodes.Inspect.outgoing[0].name = '旧版自定义判断'
  const unclassified = await importWorkflowJson(JSON.stringify(legacy))
  assert.equal(unclassified.unclassifiedBranches, 1)
  const legacyModel = await moddle.fromXML(unclassified.xml)
  assert.equal(
    legacyModel.rootElement.rootElements[0].flowElements.find((item) => item.id === 'Yes1').name,
    '旧版自定义判断',
  )
  const nested = {
    start: 'Start',
    nodes: {
      Start: {
        id: 'Start',
        kind: 'start',
        scope: 'Process',
        outgoing: [{ id: 'ToSub', target: 'Sub' }],
      },
      Sub: {
        id: 'Sub',
        kind: 'subprocess',
        scope: 'Process',
        start: 'Inner',
        outgoing: [{ id: 'Done', target: 'Solved' }],
      },
      Inner: {
        id: 'Inner',
        kind: 'start',
        scope: 'Sub',
        outgoing: [{ id: 'InnerFlow', target: 'End' }],
      },
      End: { id: 'End', kind: 'end', scope: 'Sub', outgoing: [] },
      Solved: workflow.nodes.Solved,
    },
  }
  const sub = await moddle.fromXML((await importWorkflowJson(JSON.stringify(nested))).xml)
  assert.equal(
    sub.rootElement.rootElements[0].flowElements.find((item) => item.id === 'Sub').flowElements
      .length,
    3,
  )
  for (const mutate of [
    (data) => {
      data.nodes.Inspect.outgoing[0].target = 'Missing'
    },
    (data) => {
      data.nodes.Inspect.outgoing[0].id = 'Inspect'
    },
    (data) => {
      data.nodes.Inspect.scope = 'MissingScope'
    },
    (data) => {
      data.mode = 'invalid'
    },
    (data) => {
      data.version = 999
    },
  ]) {
    const invalid = structuredClone(workflow)
    mutate(invalid)
    await assert.rejects(importWorkflowJson(JSON.stringify(invalid)))
  }
  await assert.rejects(importWorkflowJson('{bad json'))
  await assert.rejects(importWorkflowJson('{"nodes":{},"start":"missing"}'))
  console.log(
    'PASS: JSON nodes/edges, Yes/No groups, ordering, mode, details, escaping, legacy files, subprocesses, generated layout and invalid-file rejection',
  )
} finally {
  await rm(temp, { recursive: true, force: true })
}
