// 使用真实 Moddle 与项目完整校验配置检查所有示例，而不是只检查 XML 能否解析。
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile, readdir, mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const BpmnModdle = createRequire(require.resolve('bpmn-js/package.json'))('bpmn-moddle')
const Linter = require('bpmnlint/lib/linter')
const directory = await mkdtemp(path.join(tmpdir(), 'diagnostic-lint-'))
const output = path.join(directory, 'lint.cjs')
await build({
  entryPoints: ['src/views/ProcessDesigner/Lint/index.ts'],
  outfile: output,
  bundle: true,
  platform: 'node',
  format: 'cjs',
  alias: { '@': path.resolve('src') },
})
const { default: configuration } = require(output)
const moddle = new BpmnModdle({
  flowable: JSON.parse(await readFile('src/views/ProcessDesigner/flowable.json', 'utf8')),
})
for (const filename of (await readdir('src/views/ProcessDesigner/examples')).filter((file) =>
  file.endsWith('.bpmn'),
)) {
  const { rootElement, warnings } = await moddle.fromXML(
    await readFile('src/views/ProcessDesigner/examples/' + filename, 'utf8'),
  )
  assert.equal(warnings.length, 0, JSON.stringify(warnings))
  const issues = await new Linter(configuration).lint(rootElement)
  assert.deepEqual(issues, {}, filename + ': ' + JSON.stringify(issues))
  const serialized = await moddle.toXML(rootElement, { format: true })
  const roundtrip = await moddle.fromXML(serialized.xml)
  assert.equal(roundtrip.warnings.length, 0)
  if (filename === 'human-decision.bpmn') {
    assert.equal(roundtrip.elementsById.Voltage.get('flowable:humanDecision'), true)
    assert.equal(roundtrip.elementsById.VoltageConclusion.get('flowable:humanDecision'), true)
    assert.equal(roundtrip.elementsById.VoltageConclusion.get('flowable:pythonModule'), undefined)
    assert.ok(serialized.xml.includes('flowable:humanDecision="true"'))
    assert.ok(!serialized.xml.includes('camunda:'))
  }
  console.log(filename + ': all lint rules and XML round-trip passed')
}
// 普通 BPMN 并行汇合仍需提示，避免为诊断示例放宽标准流程规则。
const process = moddle.create('bpmn:Process', { id: 'Plain' })
const task = moddle.create('bpmn:Task', { id: 'Task' })
task.$parent = process
task.incoming = [{}, {}]
process.flowElements = [task]
const messages = []
configuration.resolver
  .resolveRule('bpmnlint', 'fake-join')()
  .check(task, { report: (...args) => messages.push(args) })
assert.equal(messages.length, 1)
