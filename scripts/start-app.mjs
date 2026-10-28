import { spawn } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  openSync,
  closeSync,
  appendFileSync,
  readFileSync,
  writeFileSync,
  renameSync,
  unlinkSync,
  statSync,
} from 'node:fs'
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

async function checkCommand(
  name,
  command,
  args,
  { timeout = 15000, echo = true, cwd = root } = {},
) {
  const entry = launch(name, command, args, { essential: false, echo, cwd })
  let output = ''
  // 静默检查仍写日志；需要返回值的命令才通过管道收集输出。
  entry.child.stdout?.on('data', (chunk) => (output += chunk))
  entry.child.stderr?.on('data', (chunk) => (output += chunk))
  return new Promise((resolve, reject) => {
    let settled = false
    let timeoutError
    const timer = setTimeout(() => {
      timeoutError = new Error(`命令执行超时 / Command timed out: ${entry.logPath}`)
      // 先停止准备进程再释放锁，避免下次启动与未结束的安装或构建同时写入。
      void terminate(entry).then(() => finish(timeoutError))
    }, timeout)
    const finish = (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      children.delete(entry)
      if (timeoutError || error) reject(timeoutError || error)
      else resolve(output)
    }
    entry.child.once('error', (error) =>
      finish(new Error(`${error.message}\n日志 / Log: ${entry.logPath}`)),
    )
    entry.child.once('close', (code) =>
      finish(
        code === 0 ? null : new Error(`命令执行失败 / Command failed (${code}): ${entry.logPath}`),
      ),
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
  const directory = join(root, 'backend', '.local', 'venv')
  const local = join(directory, windows ? 'Scripts/python.exe' : 'bin/python')
  const requirements = join(root, 'backend', 'requirements-flowable.txt')
  requireFile(requirements, '请恢复 Python 依赖清单 / Restore backend/requirements-flowable.txt')
  const release = acquireSetupLock('python', 'Python')
  try {
    let usable = false
    if (existsSync(local)) {
      try {
        await checkCommand(
          'python-check',
          local,
          [
            '-I',
            '-c',
            'import os, sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"; ' +
              'assert sys.prefix != sys.base_prefix and ' +
              'os.path.normcase(os.path.realpath(sys.prefix)) == ' +
              'os.path.normcase(os.path.realpath(sys.argv[1])), "Invalid project virtual environment"',
            directory,
          ],
          { echo: false },
        )
        usable = true
      } catch {
        assertRunning()
      }
    }
    if (!usable) {
      const base = await findPython()
      if (existsSync(directory)) {
        // 迁移或中断创建留下的环境可能包含旧机器路径，保留备份后重新创建。
        const backup = `${directory}.backup-${Date.now()}`
        renameSync(directory, backup)
        log(`原 Python 环境已备份 / Previous Python environment backed up: ${backup}`)
      }
      log('首次准备：创建项目 Python 环境 / First setup: creating project Python environment...')
      try {
        await checkCommand('python-setup', base, ['-I', '-m', 'venv', directory], {
          timeout: 120000,
        })
      } catch (error) {
        throw new Error(
          `无法创建 Python 虚拟环境，请确认所选 Python 提供 venv/ensurepip / ` +
            `Cannot create virtual environment; ensure the selected Python includes venv/ensurepip.\n${error.message}`,
        )
      }
    }
    if (!(await pythonDependenciesReady(local, requirements))) {
      log(
        '正在安装平台 Python 依赖（需要软件源连接） / Installing platform Python dependencies (package index access required)...',
      )
      try {
        await checkCommand('python-pip-check', local, ['-I', '-m', 'pip', '--version'], {
          echo: false,
        })
      } catch {
        assertRunning()
        await checkCommand('python-ensurepip', local, ['-I', '-m', 'ensurepip'], {
          timeout: 120000,
        })
      }
      try {
        await checkCommand(
          'python-install',
          local,
          [
            '-I',
            '-m',
            'pip',
            'install',
            '--require-virtualenv',
            '--disable-pip-version-check',
            '-r',
            requirements,
          ],
          { timeout: 600000 },
        )
      } catch (error) {
        throw new Error(
          `Python 依赖安装失败，请查看上方错误并检查网络、代理或 PIP_INDEX_URL 后重新启动 / ` +
            `Python dependency installation failed; check the output, network, proxy or PIP_INDEX_URL and restart.\n${error.message}`,
        )
      }
      if (!(await pythonDependenciesReady(local, requirements))) {
        throw new Error(
          `安装后 Python 依赖检查仍失败 / Python dependencies still fail validation after installation.\n` +
            `日志 / Logs: ${join(logDirectory, 'python-dependencies.log')}`,
        )
      }
    }
    log(`平台 Python 环境已就绪 / Platform Python environment ready: ${local}`)
    return local
  } finally {
    release()
  }
}

function acquireSetupLock(name, label) {
  const path = join(root, 'backend', '.local', `${name}-setup.lock`)
  try {
    const owner = JSON.parse(readFileSync(path, 'utf8'))
    if (!Number.isInteger(owner.pid) || owner.pid <= 0) throw new Error('Invalid setup lock')
    try {
      process.kill(owner.pid, 0)
    } catch (error) {
      if (error.code !== 'ESRCH') throw error
      unlinkSync(path)
    }
  } catch (error) {
    if (error.code !== 'ENOENT') {
      throw new Error(
        `无法读取 ${label} 准备锁，请确认没有其他准备进程后移除此文件 / ` +
          `Cannot read ${label} setup lock; remove this file only after confirming no other setup is running.\n${path}\n${error.message}`,
      )
    }
  }
  let descriptor
  try {
    descriptor = openSync(path, 'wx')
  } catch (error) {
    if (error.code !== 'EEXIST') throw error
    throw new Error(
      `另一个启动器正在准备 ${label}，请等待其完成 / ` +
        `Another launcher is preparing ${label}; wait for it to finish.\n${path}`,
    )
  }
  try {
    writeFileSync(descriptor, JSON.stringify({ pid: process.pid }))
  } finally {
    closeSync(descriptor)
  }
  return () => unlinkSync(path)
}

async function pythonDependenciesReady(python, requirements) {
  try {
    await checkCommand(
      'python-dependencies',
      python,
      [
        '-I',
        '-c',
        'import sys; from pathlib import Path; from importlib.metadata import version; ' +
          'requirements = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(); ' +
          'pins = [line.strip().split("==") for line in requirements if line.strip() and not line.lstrip().startswith("#")]; ' +
          'assert all(version(name) == expected for name, expected in pins), "Dependency version mismatch"; ' +
          'from flowable.external_worker_client import ExternalWorkerClient',
        requirements,
      ],
      { echo: false },
    )
    await checkCommand('python-dependencies', python, ['-I', '-m', 'pip', 'check'], { echo: false })
    return true
  } catch {
    assertRunning()
    return false
  }
}

async function findPython() {
  const candidates = process.env.PYTHON
    ? [process.env.PYTHON]
    : windows
      ? ['python', 'py']
      : ['python3', 'python']
  for (const command of candidates) {
    try {
      const output = await checkCommand('python-check', command, [
        ...(command === 'py' ? ['-3'] : []),
        '-I',
        '-c',
        'import json, sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"; print(json.dumps(sys.executable))',
      ])
      return JSON.parse(output.trim())
    } catch {
      assertRunning()
    }
  }
  throw new Error(
    `未找到可用的 Python 3.9+，请先安装 Python / No usable Python 3.9+ found; install Python first.\n` +
      `可设置 PYTHON 为创建项目环境所用的解释器路径；平台依赖将自动安装 / ` +
      `Set PYTHON to the interpreter path used to create the project environment; platform dependencies install automatically.\n` +
      `日志 / Log: ${join(logDirectory, 'python-check.log')}`,
  )
}

async function prepareFlowableJar(jar) {
  const pending = join(root, 'backend', '.local', 'flowable-build.pending')
  const pom = join(root, 'flowable-runtime', 'pom.xml')
  // 编译目标改变后不能复用旧字节码；Git 更新构建配置后自动重建一次。
  const ready = () =>
    existsSync(jar) &&
    !existsSync(pending) &&
    (!existsSync(pom) || statSync(jar).mtimeMs >= statSync(pom).mtimeMs)
  if (ready()) return
  const release = acquireSetupLock('flowable', 'Flowable')
  try {
    if (ready()) return
    const cwd = join(root, 'flowable-runtime')
    requireFile(pom, '请恢复引擎源码 / Restore flowable-runtime sources')
    // Windows 的 Maven 入口是批处理；只把固定命令交给 cmd，项目路径通过 cwd 传递。
    const command = windows ? process.env.ComSpec || 'cmd.exe' : 'mvn'
    const args = (build) =>
      windows
        ? [
            '/d',
            '/s',
            '/c',
            build ? 'mvn.cmd -B -ntp -DskipTests clean package' : 'mvn.cmd -version',
          ]
        : build
          ? ['-B', '-ntp', '-DskipTests', 'clean', 'package']
          : ['-version']
    try {
      const output = await checkCommand('maven-check', command, args(false), { cwd })
      const version = /Apache Maven (\d+)\.(\d+)/.exec(output)
      const javaVersion = /Java version:\s*(\d+)/i.exec(output)
      if (
        !version ||
        !(Number(version[1]) > 3 || (Number(version[1]) === 3 && Number(version[2]) >= 9)) ||
        !javaVersion ||
        Number(javaVersion[1]) < 17
      ) {
        throw new Error('Maven 3.9+ running on JDK 17+ required')
      }
    } catch (error) {
      throw new Error(
        `构建 Flowable 需要 Maven 3.9+ 和 JDK 17+，请检查 PATH/JAVA_HOME / ` +
          `Building Flowable requires Maven 3.9+ on JDK 17+; check PATH/JAVA_HOME.\n${error.message}`,
      )
    }
    log(
      '正在准备 Flowable 引擎，可能下载 Java 依赖，请稍候 / ' +
        'Preparing Flowable; Java dependencies may be downloaded, please wait...',
    )
    // 强制退出时可能来不及清理 JAR；标记让下次启动重试，而不复用中断的打包产物。
    writeFileSync(pending, String(process.pid))
    try {
      await checkCommand('flowable-build', command, args(true), { cwd, timeout: 900000 })
      requireFile(jar, '构建未生成可执行引擎 / Build did not produce the runtime JAR')
      unlinkSync(pending)
    } catch (error) {
      assertRunning()
      // Maven 可能在打包中途失败；保留失败产物，避免下次误把普通或不完整 JAR 当成可执行引擎。
      if (existsSync(jar)) renameSync(jar, `${jar}.failed-${Date.now()}`)
      throw new Error(
        `Flowable 自动构建失败，请检查上方错误、Maven 软件源和网络后重试 / ` +
          `Automatic Flowable build failed; check the output, Maven repositories and network, then retry.\n${error.message}`,
      )
    }
    log(`Flowable 引擎已准备好 / Flowable runtime ready: ${jar}`)
  } finally {
    release()
  }
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
  let java
  const jar = join(root, 'flowable-runtime', 'target', 'diagnostic-flowable-1.0.0.jar')
  if (!engine.healthy && !explicitFlowable) {
    java = process.env.JAVA_HOME
      ? join(process.env.JAVA_HOME, 'bin', windows ? 'java.exe' : 'java')
      : 'java'
    try {
      const version = await checkCommand('java-check', java, ['-version'])
      const major = Number(/version\s+"(\d+)/i.exec(version)?.[1])
      if (!Number.isInteger(major) || major < 17) throw new Error('Java 17+ required')
    } catch {
      throw new Error(
        `需要 Java 17+，请检查 JAVA_HOME/PATH / Java 17+ required; check JAVA_HOME/PATH.\n${join(logDirectory, 'java-check.log')}`,
      )
    }
    await prepareFlowableJar(jar)
  }
  const python = backend.healthy ? null : await pythonCommand()
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
