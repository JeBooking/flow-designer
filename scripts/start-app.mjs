import { spawn } from 'node:child_process'
import { existsSync, mkdirSync, openSync, closeSync, appendFileSync } from 'node:fs'
import { createConnection } from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'

const root = dirname(dirname(fileURLToPath(import.meta.url)))
const windows = process.platform === 'win32'
const production = process.argv.includes('--production')
const logDirectory = join(root, 'backend', '.local', 'logs')
const children = new Set()
const controller = new AbortController()
const backendUrl = 'http://127.0.0.1:8765'
const explicitFlowable = Object.hasOwn(process.env, 'FLOWABLE_URL')
const flowableUrl = process.env.FLOWABLE_URL ?? 'http://127.0.0.1:8080'
const credentials = Buffer.from(
  `${process.env.FLOWABLE_USER ?? 'diagnostic'}:${process.env.FLOWABLE_PASSWORD ?? 'local-demo'}`,
).toString('base64')
let stopping = false
let shutdownPromise

function assertRunning() {
  if (stopping) throw new Error('启动已取消 / Startup cancelled')
}

function log(message) {
  console.log(`[app] ${message}`)
}

function requireFile(path, instruction) {
  if (!existsSync(path)) throw new Error(`缺少文件 / Missing file: ${path}\n${instruction}`)
}

function launch(name, command, args, { cwd = root, essential = true, echo = false } = {}) {
  assertRunning()
  const logPath = join(logDirectory, `${name}.log`)
  appendFileSync(logPath, `\n--- ${new Date().toISOString()} ---\n`)
  const descriptor = openSync(logPath, 'a')
  let child
  try {
    child = spawn(command, args, {
      cwd,
      env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONUTF8: '1' },
      shell: false,
      windowsHide: true,
      // Unix 使用独立进程组，关闭后端时也能回收它创建的 worker。
      detached: !windows,
      stdio: ['ignore', echo ? 'pipe' : descriptor, echo ? 'pipe' : descriptor],
    })
  } finally {
    closeSync(descriptor)
  }
  const entry = { child, logPath, name }
  children.add(entry)
  if (echo) {
    for (const [stream, output] of [
      [child.stdout, process.stdout],
      [child.stderr, process.stderr],
    ]) {
      stream.on('data', (chunk) => {
        appendFileSync(logPath, chunk)
        output.write(chunk)
      })
    }
  }
  child.on('error', (error) => {
    if (essential && !stopping) {
      console.error(`[app] ${name} 启动失败 / Failed to start: ${error.message}\n${logPath}`)
      void shutdown(1)
    }
  })
  child.on('exit', (code, signal) => {
    if (essential && !stopping) {
      console.error(
        `[app] ${name} 意外退出 / Unexpected exit (${code ?? signal}). 日志 / Log: ${logPath}`,
      )
      void shutdown(1)
    }
  })
  return entry
}

async function terminate(entry) {
  const { child } = entry
  if (!child.pid) return
  if (windows) {
    // 仅按当前启动器持有的 PID 回收树；绝不按进程名称清理或触碰复用的服务。
    if (child.exitCode !== null || child.signalCode !== null) return
    await new Promise((resolve) => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        shell: false,
        windowsHide: true,
        stdio: 'ignore',
      })
      killer.once('error', resolve)
      killer.once('close', resolve)
    })
  } else {
    try {
      process.kill(-child.pid, 'SIGTERM')
    } catch (error) {
      if (error.code !== 'ESRCH') console.error(error.message)
    }
    // 后端会关闭独立进程组中的 worker；保留清理时间后才强制回收进程组。
    const deadline = Date.now() + 20000
    while (child.exitCode === null && child.signalCode === null && Date.now() < deadline) {
      await delay(100)
    }
    try {
      process.kill(-child.pid, 'SIGKILL')
    } catch (error) {
      if (error.code !== 'ESRCH') console.error(error.message)
    }
  }
}

function shutdown(code) {
  if (shutdownPromise) return shutdownPromise
  stopping = true
  controller.abort()
  shutdownPromise = (async () => {
    log('正在停止自有服务 / Stopping owned services...')
    await Promise.allSettled([...children].reverse().map(terminate))
    process.exit(code)
  })()
  return shutdownPromise
}

process.on('SIGINT', () => void shutdown(130))
process.on('SIGTERM', () => void shutdown(143))

async function checkCommand(name, command, args) {
  const entry = launch(name, command, args, { essential: false, echo: true })
  let output = ''
  entry.child.stdout.on('data', (chunk) => (output += chunk))
  entry.child.stderr.on('data', (chunk) => (output += chunk))
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      void terminate(entry)
      reject(new Error(`依赖检查超时 / Dependency check timed out: ${entry.logPath}`))
    }, 15000)
    const finish = (error) => {
      clearTimeout(timer)
      children.delete(entry)
      if (error) reject(error)
      else resolve(output)
    }
    entry.child.once('error', finish)
    entry.child.once('close', (code) =>
      finish(code === 0 ? null : new Error(`依赖检查失败 / Check failed: ${entry.logPath}`)),
    )
  })
}

async function probe(url, isHealthy, headers = {}) {
  assertRunning()
  try {
    const response = await fetch(url, {
      headers,
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(2500)]),
      redirect: 'error',
    })
    let body
    try {
      body = await response.json()
    } catch {
      return { healthy: false, reachable: true, reason: `HTTP ${response.status}, invalid JSON` }
    }
    const validation = isHealthy(body)
    return {
      healthy: response.ok && validation === true,
      reachable: true,
      reason: `HTTP ${response.status}, ${
        typeof validation === 'string'
          ? validation
          : response.ok
            ? 'unexpected service response'
            : 'access denied or unavailable'
      }`,
    }
  } catch (error) {
    assertRunning()
    return { healthy: false, reachable: false, reason: error.message }
  }
}

async function portOccupied(url) {
  const address = new URL(url)
  return new Promise((resolve) => {
    const socket = createConnection({
      host: address.hostname,
      port: Number(address.port || (address.protocol === 'https:' ? 443 : 80)),
    })
    const finish = (occupied) => {
      socket.destroy()
      resolve(occupied)
    }
    socket.setTimeout(1500, () => finish(true))
    socket.once('connect', () => finish(true))
    socket.once('error', () => finish(false))
  })
}

async function waitHealthy(name, health, timeout) {
  const deadline = Date.now() + timeout
  let result
  while (Date.now() < deadline) {
    assertRunning()
    result = await health()
    if (result.healthy) return
    await delay(500, undefined, { signal: controller.signal })
  }
  throw new Error(
    `${name} 健康检查超时 / Health check timed out: ${result?.reason}\n日志 / Logs: ${logDirectory}`,
  )
}

async function pythonCommand() {
  const local = join(
    root,
    'backend',
    '.local',
    'venv',
    windows ? 'Scripts/python.exe' : 'bin/python',
  )
  const candidates = process.env.PYTHON
    ? [process.env.PYTHON]
    : existsSync(local)
      ? [local]
      : windows
        ? ['python', 'py']
        : ['python3', 'python']
  for (const command of candidates) {
    try {
      await checkCommand('python-check', command, [
        '-c',
        'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"; from flowable.external_worker_client import ExternalWorkerClient; print(sys.executable)',
      ])
      return command
    } catch {
      assertRunning()
    }
  }
  throw new Error(
    `需要 Python 3.9+ 与 Flowable SDK / Python 3.9+ and Flowable SDK required.\n` +
      `首次准备环境 / Prepare once: python -m venv backend/.local/venv; ` +
      `use its Python with -m pip install -r backend/requirements-flowable.txt\n` +
      `可设置 PYTHON 为解释器路径 / Set PYTHON to the interpreter path.\n日志 / Log: ${join(logDirectory, 'python-check.log')}`,
  )
}

function normalizedEngineUrl(value) {
  return new URL(value).href.replace(/\/+$/, '')
}

async function main() {
  mkdirSync(logDirectory, { recursive: true })
  log(`检查运行环境 / Checking prerequisites (${production ? 'production' : 'development'})...`)
  if (process.argv.slice(2).some((arg) => arg !== '--production')) {
    throw new Error('未知参数 / Unknown argument. Use pnpm dev, pnpm dev:frontend or pnpm start.')
  }
  const flowableAddress = new URL(flowableUrl)
  if (!['http:', 'https:'].includes(flowableAddress.protocol)) {
    throw new Error('FLOWABLE_URL 必须是 HTTP(S) 地址 / FLOWABLE_URL must be an HTTP(S) URL')
  }
  const vite = join(root, 'node_modules', 'vite', 'bin', 'vite.js')
  requireFile(join(root, 'backend', 'server.py'), '请恢复后端文件 / Restore backend/server.py')
  if (production) {
    requireFile(join(root, 'dist', 'index.html'), '请先构建 / Build first: pnpm build')
  } else {
    requireFile(vite, '请先准备前端依赖 / Prepare frontend dependencies first: pnpm install')
  }
  const backendHealth = () =>
    probe(`${backendUrl}/api/health`, (body) => {
      if (body?.ok !== true || body?.service !== 'diagnosis-backend') return false
      if (typeof body.flowableUrl !== 'string') {
        return '后端健康接口缺少 flowableUrl，请重启当前版本 / Restart current backend: health response requires flowableUrl'
      }
      try {
        if (normalizedEngineUrl(body.flowableUrl) === normalizedEngineUrl(flowableUrl)) return true
      } catch {
        // 旧版本或异常配置的健康接口不能作为可安全复用的依据。
      }
      return '后端 Flowable 配置冲突，请使用相同 FLOWABLE_URL 重启后端 / Backend Flowable configuration conflict: restart backend with the same FLOWABLE_URL'
    })
  const flowableHealth = () =>
    probe(
      `${flowableUrl.replace(/\/$/, '')}/process-api/repository/process-definitions?size=1`,
      (body) => Array.isArray(body?.data) && Number.isInteger(body?.total) && body.total >= 0,
      { Authorization: `Basic ${credentials}` },
    )
  const backend = await backendHealth()
  const engine = await flowableHealth()
  if (!backend.healthy && (backend.reachable || (await portOccupied(backendUrl)))) {
    throw new Error(
      `8765 已被未通过身份检查的服务占用 / Unrecognized service on port 8765: ${backend.reason}`,
    )
  }
  if (
    !engine.healthy &&
    !explicitFlowable &&
    (engine.reachable || (await portOccupied(flowableUrl)))
  ) {
    throw new Error(
      `8080 服务未通过 Flowable 认证健康检查 / Flowable check failed on port 8080: ${engine.reason}`,
    )
  }
  const python = backend.healthy ? null : await pythonCommand()
  let java
  const jar = join(root, 'flowable-runtime', 'target', 'diagnostic-flowable-1.0.0.jar')
  if (!engine.healthy && !explicitFlowable) {
    requireFile(
      jar,
      '首次准备 / Prepare once: cd flowable-runtime, then mvn package (Java 21, Maven 3.9+)',
    )
    java = process.env.JAVA_HOME
      ? join(process.env.JAVA_HOME, 'bin', windows ? 'java.exe' : 'java')
      : 'java'
    try {
      const version = await checkCommand('java-check', java, ['-version'])
      const major = Number(/version\s+"(\d+)/i.exec(version)?.[1])
      if (!Number.isInteger(major) || major < 21) throw new Error('Java 21+ required')
    } catch {
      throw new Error(
        `需要 Java 21+，请检查 JAVA_HOME/PATH / Java 21+ required; check JAVA_HOME/PATH.\n${join(logDirectory, 'java-check.log')}`,
      )
    }
  }
  if (engine.healthy) log('复用已认证 Flowable / Reusing authenticated Flowable')
  else if (explicitFlowable) {
    log('等待指定 Flowable / Waiting for configured Flowable...')
    await waitHealthy('External Flowable', flowableHealth, 120000)
  } else {
    log('启动本地 Flowable / Starting local Flowable...')
    launch('flowable', java, ['-jar', jar], { cwd: join(root, 'flowable-runtime') })
    await waitHealthy('Flowable', flowableHealth, 120000)
  }
  if (backend.healthy) log('复用 Python 后端 / Reusing Python backend')
  else {
    log('启动 Python 后端 / Starting Python backend...')
    launch('backend', python, [join(root, 'backend', 'server.py')])
    await waitHealthy('Python backend', backendHealth, 30000)
  }
  if (!production) {
    log('启动前端 / Starting frontend...')
    launch(
      'frontend',
      process.execPath,
      [vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
      {
        echo: true,
      },
    )
    await waitHealthy('Frontend', () => probeFrontend(), 30000)
  }
  assertRunning()
  log(`就绪 / Ready: ${production ? backendUrl : 'http://127.0.0.1:5173'}/vue-bpmn-designer/`)
  log(`后端 / Backend: ${backendUrl}; 日志 / Logs: ${logDirectory}`)
  log('按 Ctrl+C 停止自有服务 / Press Ctrl+C to stop owned services')
  // 全部服务被复用时仍保留启动器，以维持一致的 Ctrl+C 生命周期。
  setInterval(() => {}, 60000)
}

async function probeFrontend() {
  assertRunning()
  try {
    const response = await fetch('http://127.0.0.1:5173/vue-bpmn-designer/', {
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(2500)]),
    })
    return { healthy: response.ok, reason: `HTTP ${response.status}` }
  } catch (error) {
    assertRunning()
    return { healthy: false, reason: error.message }
  }
}

main().catch((error) => {
  if (!stopping) console.error(`[app] ${error.message}\n日志目录 / Log directory: ${logDirectory}`)
  void shutdown(1)
})
