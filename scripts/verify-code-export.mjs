// 对真实 Moddle 模型、ZIP 和导出的 Python 工程执行端到端验证。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, writeFile, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

const require = createRequire(import.meta.url)
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const BpmnModdle = createRequire(require.resolve('bpmn-js/package.json'))('bpmn-moddle')
const root = process.cwd()
const temp = await mkdtemp(path.join(tmpdir(), 'diagnostic-export-'))
await build({
  entryPoints: [
    'src/views/ProcessDesigner/CodeGeneration/generate.ts',
    'src/views/ProcessDesigner/CodeGeneration/archive.ts',
  ],
  outdir: temp,
  outExtension: { '.js': '.mjs' },
  bundle: true,
  platform: 'node',
  format: 'esm',
  alias: { '@': path.join(root, 'src') },
  plugins: [
    {
      name: 'raw-python',
      setup(builder) {
        builder.onResolve({ filter: /\.py\?raw$/ }, (args) => ({
          path: args.path.startsWith('/backend/')
            ? path.join(root, args.path.slice(1, -4))
            : path.resolve(args.resolveDir, args.path.slice(0, -4)),
          namespace: 'raw',
        }))
        builder.onLoad({ filter: /.*/, namespace: 'raw' }, async (args) => ({
          contents: await readFile(args.path, 'utf8'),
          loader: 'text',
        }))
      },
    },
  ],
})
const { generateProject } = await import(pathToFileURL(path.join(temp, 'generate.mjs')))
const { createArchive } = await import(pathToFileURL(path.join(temp, 'archive.mjs')))
const descriptor = JSON.parse(await readFile('src/views/ProcessDesigner/flowable.json', 'utf8'))
const moddle = new BpmnModdle({ flowable: descriptor })
const image =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII='
const node = (type, id, attributes = {}) => moddle.create('bpmn:' + type, { id, ...attributes })
const start = node('StartEvent', 'Start')
const inspect = node('Task', 'Inspect', {
  name: '检查 "电压"',
  'flowable:diagnosisKind': 'investigation',
  'flowable:observation': '电压',
  'flowable:acquisition': '使用电压表',
  'flowable:assessment': '对照额定电压判断',
  'flowable:referenceImage': image,
})
const task = (id, kind, attributes = {}) =>
  node('Task', id, { name: id, 'flowable:diagnosisKind': kind, ...attributes })
const conclusion = task('Conclusion', 'conclusion', { 'flowable:conclusionText': '电源异常' })
const repair = task('Repair', 'remediation')
const solved = task('Solved', 'problemSolved')
const escalation = task('Escalation', 'escalation')
const jump = task('Jump', 'jump')
const action = task('Action', 'investigationAction', { 'flowable:actionText': '重新采集' })
const deep = task('Deep', 'deepDiagnosis')
const flow = (id, sourceRef, targetRef) =>
  node('SequenceFlow', id, { sourceRef, targetRef, name: id })
const elements = [
  start,
  inspect,
  conclusion,
  repair,
  solved,
  escalation,
  jump,
  action,
  deep,
  flow('begin', start, inspect),
  flow('normal', inspect, conclusion),
  flow('bad', inspect, escalation),
  flow('retry', inspect, action),
  flow('again', action, inspect),
  flow('handle', conclusion, repair),
  flow('fixed', repair, solved),
  flow('handoff', repair, jump),
  flow('deeper', repair, deep),
  flow('done', deep, solved),
]
const processModel = node('Process', 'Process', { flowElements: elements })
const definitions = node('Definitions', 'Definitions', {
  rootElements: [processModel],
  targetNamespace: 'test',
})
const { xml } = await moddle.toXML(definitions)
const { rootElement } = await moddle.fromXML(xml)
const files = generateProject(rootElement, xml)
const zip = createArchive(files)
await writeFile(path.join(temp, 'project.zip'), Buffer.from(await zip.arrayBuffer()))
assert.equal(JSON.parse(files['workflow.json']).nodes.Inspect.name, '检查 "电压"')
const invalid = node('ParallelGateway', 'Unsupported')
processModel.flowElements = [...elements, invalid]
assert.throws(() => generateProject(definitions, xml), /Unsupported/)
processModel.flowElements = elements.filter((e) => e.id !== 'begin')
assert.throws(() => generateProject(definitions, xml), /Start/)
processModel.flowElements = elements
inspect.set('flowable:assessment', '')
assert.throws(() => generateProject(definitions, xml), /Inspect/)
inspect.set('flowable:assessment', '对照额定电压判断')
const innerStart = node('StartEvent', 'InnerStart')
const innerEnd = node('EndEvent', 'InnerEnd')
const sub = node('SubProcess', 'Sub', {
  flowElements: [innerStart, innerEnd, flow('inner', innerStart, innerEnd)],
})
processModel.flowElements = [
  start,
  sub,
  solved,
  flow('enter', start, sub),
  flow('exit', sub, solved),
]
const nested = generateProject(definitions, xml)
await writeFile(path.join(temp, 'nested.json'), nested['workflow.json'])
const result = spawnSync(process.env.PYTHON || 'python', ['scripts/code-export-smoke.py', temp], {
  stdio: 'inherit',
  env: { ...process.env, PYTHONUTF8: '1' },
})
assert.equal(result.status, 0, 'Generated Python verification failed')
console.log('Moddle parsing, export validation, ZIP and Python runtime checks passed.')
console.log('Temporary generated project:', temp)
