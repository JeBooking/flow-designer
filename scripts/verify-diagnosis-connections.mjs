import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const BpmnModdle = createRequire(require.resolve('bpmn-js/package.json'))('bpmn-moddle')
const bundle = await build({
  entryPoints: ['src/views/ProcessDesigner/Diagnosis/model.ts'],
  bundle: true,
  platform: 'node',
  format: 'cjs',
  write: false,
  alias: { '@': path.resolve('src') },
})
const module = { exports: {} }
new Function('module', 'exports', 'require', bundle.outputFiles[0].text)(
  module,
  module.exports,
  require,
)
const { isDiagnosisConnectionAllowed, diagnosisKinds } = module.exports
const moddle = new BpmnModdle({
  flowable: require('../src/views/ProcessDesigner/flowable.json'),
})
const kinds = ['start', ...Object.keys(diagnosisKinds)]
// 固定业务预期，避免两侧同时误改后差分仍通过。
const expected = {
  start: '010000000',
  investigation: '011100101',
  investigationAction: '010000000',
  conclusion: '000010101',
  remediation: '000011111',
  deepDiagnosis: '000011111',
  jump: '000011111',
  problemSolved: '000000000',
  escalation: '000000000',
}
assert.deepEqual(kinds, Object.keys(expected))
const backend = spawnSync(
  process.env.PYTHON || 'python',
  [
    '-B',
    '-c',
    `import json, sys
sys.path.insert(0, 'backend')
from flowable_bridge import is_diagnosis_connection_allowed
kinds = json.loads(sys.argv[1])
print(json.dumps([[is_diagnosis_connection_allowed(a, b) for b in kinds] for a in kinds]))`,
    JSON.stringify(kinds),
  ],
  { encoding: 'utf8', env: { ...process.env, PYTHONUTF8: '1' } },
)
assert.equal(backend.status, 0, backend.error?.message || backend.stderr)
const matrix = JSON.parse(backend.stdout)
const start = moddle.create('bpmn:StartEvent', { id: 'Start' })
const node = (kind, id) =>
  kind === 'start' ? start : moddle.create('bpmn:Task', { id, 'flowable:diagnosisKind': kind })
for (const [i, sourceKind] of kinds.entries()) {
  for (const [j, targetKind] of kinds.entries()) {
    const source = node(sourceKind, 'Source')
    const target = node(targetKind, 'Target')
    const label = `${sourceKind} -> ${targetKind}`
    assert.equal(matrix[i][j], expected[sourceKind][j] === '1', `Backend: ${label}`)
    assert.equal(isDiagnosisConnectionAllowed(source, target), matrix[i][j], label)
    assert.equal(isDiagnosisConnectionAllowed(source, source), false, 'Reject self connections')
  }
}
const plain = moddle.create('bpmn:Task', { id: 'Plain' })
const subprocess = moddle.create('bpmn:SubProcess', { id: 'Sub' })
assert.equal(isDiagnosisConnectionAllowed(start, subprocess), true)
assert.equal(isDiagnosisConnectionAllowed(plain, subprocess), true)
assert.equal(isDiagnosisConnectionAllowed(plain, plain), true)
assert.equal(isDiagnosisConnectionAllowed(subprocess, node('problemSolved', 'Solved')), true)
assert.equal(isDiagnosisConnectionAllowed(subprocess, node('investigation', 'Inspect')), false)
assert.equal(isDiagnosisConnectionAllowed(start, node('remediation', 'Action')), false)
console.log(
  'PASS: 81 frontend/backend connection pairs, fixed business expectations and generic BPMN boundaries',
)
