// 使用编辑器自身的导入器生成执行包；业务工程无需依赖本脚本或 Flowable。
import { createRequire } from 'node:module'
import { access, mkdir, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawnSync } from 'node:child_process'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const project = path.join(root, 'backend/examples/cooling_project')
const options = { mode: 'parallel', python: 'python' }
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index]?.replace(/^--/, '')
  const value = process.argv[index + 1]
  if (!Object.hasOwn(options, key) || !value)
    throw new Error('Use --mode parallel|serial and/or --python EXECUTABLE')
  options[key] = value
}
if (!['parallel', 'serial'].includes(options.mode))
  throw new Error('Mode must be parallel or serial')
const businessPython = path.join(
  project,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
try {
  await access(businessPython)
} catch {
  const created = spawnSync(
    options.python,
    ['-X', 'utf8', '-m', 'venv', '--without-pip', path.join(project, '.venv')],
    { cwd: root, encoding: 'utf8' },
  )
  if (created.error || created.status !== 0)
    throw new Error(created.error?.message || created.stderr)
}
const output = path.join(root, 'backend/.local/cooling-example-' + options.mode)
await mkdir(output, { recursive: true })
const temporaryRoot = path.resolve(tmpdir())
const temporary = await mkdtemp(path.join(temporaryRoot, 'cooling-prepare-'))
try {
  const require = createRequire(import.meta.url)
  const { build } = createRequire(require.resolve('vite/package.json'))('esbuild')
  await build({
    entryPoints: [path.join(root, 'src/views/ProcessDesigner/CodeGeneration/projectDirectory.ts')],
    outfile: path.join(temporary, 'import.mjs'),
    bundle: true,
    platform: 'node',
    format: 'esm',
    alias: { '@': path.join(root, 'src') },
  })
  const { importWorkflowDirectory } = await import(
    pathToFileURL(path.join(temporary, 'import.mjs'))
  )
  const files = []
  const walk = async (relative = '') => {
    for (const entry of await readdir(path.join(project, relative), { withFileTypes: true })) {
      if (entry.name.startsWith('.') || entry.name === '__pycache__' || entry.name === 'output')
        continue
      const name = path.posix.join(relative, entry.name)
      if (entry.isDirectory()) await walk(name)
      else
        files.push({
          path: 'cooling_project/' + name,
          read: async () => {
            const bytes = await readFile(path.join(project, name))
            if (name !== 'workflow.json') return new Uint8Array(bytes)
            const definition = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, ''))
            return new TextEncoder().encode(JSON.stringify({ ...definition, mode: options.mode }))
          },
        })
    }
  }
  await walk()
  const restored = await importWorkflowDirectory(files)
  if (restored.missingResources.length)
    throw new Error('Missing resources: ' + restored.missingResources.join(', '))
  await writeFile(path.join(output, 'source.bpmn'), restored.xml)
  const prepare = String.raw`
import json, sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
root, project, output, executable = map(Path, sys.argv[1:])
sys.path.insert(0, str(root / 'backend'))
from server import Registry
from flowable_bridge import compile_workflow
registration = {'name': 'Cooling Lab / 冷却系统示例', 'path': str(project),
                'module': 'cooling_lab.api', 'factory': 'CoolingSession', 'python': str(executable)}
try:
    request = Request('http://127.0.0.1:8765/api/projects', json.dumps(registration).encode(),
                      {'Content-Type': 'application/json'})
    with urlopen(request, timeout=10) as response:
        registered = json.load(response)
    registration_mode = 'backend API'
except HTTPError as error:
    raise RuntimeError(error.read().decode(errors='replace')) from error
except URLError as error:
    if not isinstance(error.reason, ConnectionRefusedError):
        raise
    registry = Registry(root / 'backend/.local/projects.json')
    registered = registry.register(registration)
    registration_mode = 'local registry (visible when backend starts)'
if not registered.get('ok'):
    raise RuntimeError(registered.get('traceback') or registered.get('error'))
compiled = compile_workflow((output / 'source.bpmn').read_text(encoding='utf-8'))
for name, content in compiled['files'].items():
    (output / name).write_text(content, encoding='utf-8')
print(json.dumps({'registration': registration_mode, 'projectId': registered['project']['id'],
                  'interfaces': len(registered['project']['interfaces']), 'python': str(executable),
                  'bundle': str(output)}, ensure_ascii=False, indent=2))
`
  const runner = path.join(temporary, 'prepare.py')
  await writeFile(runner, prepare)
  const executed = spawnSync(
    options.python,
    ['-X', 'utf8', runner, root, project, output, businessPython],
    {
      cwd: root,
      encoding: 'utf8',
    },
  )
  process.stdout.write(executed.stdout || '')
  process.stderr.write(executed.stderr || '')
  if (executed.error || executed.status !== 0)
    throw new Error(executed.error?.message || 'Example preparation failed')
  console.log('Prepared / 已准备: ' + output)
  console.log(
    'Worker: backend/.local/venv/Scripts/python.exe backend/flowable_worker.py "' +
      path.join(output, 'bindings.json') +
      '"',
  )
} finally {
  if (
    path.dirname(temporary) !== temporaryRoot ||
    !path.basename(temporary).startsWith('cooling-prepare-')
  )
    throw new Error('Refusing to remove an unexpected temporary path')
  await rm(temporary, { recursive: true, force: true })
}
