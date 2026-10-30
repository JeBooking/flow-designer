import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
const bundle = await build({
  stdin: {
    contents: `export { mergeExecutionHistory } from '@/views/ProcessDesigner/Execution/history'
      export { useExecutionStore } from '@/stores/modules/execution'
      export { createPinia, setActivePinia } from 'pinia'
      export { createApp, ref } from 'vue'
      export { default as persistence } from 'pinia-plugin-persistedstate'`,
    resolveDir: process.cwd(),
  },
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
const {
  mergeExecutionHistory,
  useExecutionStore,
  createPinia,
  setActivePinia,
  createApp,
  ref,
  persistence,
} = module.exports
globalThis.ref = ref
const storage = new Map()
globalThis.window = {
  localStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  },
}
function store() {
  const pinia = createPinia().use(persistence)
  createApp({}).use(pinia)
  setActivePinia(pinia)
  return useExecutionStore()
}
const first = store()
first.remember('run-1')
first.remember('run-2')
first.$persist()
const restored = store()
assert.equal(restored.runId, 'run-2')
assert.deepEqual(restored.recentRunIds, ['run-2', 'run-1'])
assert.deepEqual(Object.keys(JSON.parse(storage.get('execution-monitor'))).sort(), [
  'recentRunIds',
  'runId',
])
for (let i = 0; i < 15; i++) restored.remember(`run-${i}`)
assert.equal(restored.recentRunIds.length, 10)
restored.forget()
assert.equal(restored.runId, '')
assert.equal(restored.recentRunIds.length, 10)

const full = {
  reset: true,
  changed: true,
  cursor: 'a',
  process: {},
  variables: {
    data: [
      { id: 'value', variable: { name: 'value', value: 1 } },
      { id: 'removed', variable: { name: 'removed', value: 2 } },
    ],
  },
  activities: { data: [{ id: 'visit', activityId: 'Inspect', activityType: 'userTask' }] },
  removedVariableIds: [],
  removedActivityIds: [],
  review: { pending: true },
  pendingReviews: [{ taskId: 'task', pending: true }],
}
const original = mergeExecutionHistory(undefined, full)
const unchanged = mergeExecutionHistory(original, {
  ...full,
  reset: false,
  changed: false,
  variables: { data: [] },
  activities: { data: [] },
})
assert.equal(unchanged, original)
const completed = mergeExecutionHistory(original, {
  ...full,
  reset: false,
  cursor: 'b',
  process: { endTime: '2026-10-30T01:00:00Z' },
  variables: { data: [{ id: 'value', variable: { name: 'value', value: 3 } }] },
  activities: { data: [{ ...full.activities.data[0], endTime: '2026-10-30T01:00:00Z' }] },
  removedVariableIds: ['removed'],
  pendingReviews: [],
  review: { pending: false },
})
assert.equal(completed.variables.data.length, 1)
assert.equal(completed.variables.data[0].variable.value, 3)
assert.ok(completed.activities.data[0].endTime)
assert.equal(completed.pendingReviews.length, 0)
assert.equal(original.variables.data[0].variable.value, 1)
assert.equal(mergeExecutionHistory(completed, full).variables.data.length, 2)
console.log(
  'PASS: persisted monitor IDs without result data, recent-run bounds, incremental upsert/delete, mutable activity completion and cursor reset',
)
