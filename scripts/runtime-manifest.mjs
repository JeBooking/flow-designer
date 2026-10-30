import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, writeFileSync, renameSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export function runtimeSourceHash(root) {
  const files = ['flowable-runtime/pom.xml']
  function walk(relative) {
    for (const entry of readdirSync(path.join(root, relative), { withFileTypes: true })) {
      const name = `${relative}/${entry.name}`
      if (entry.isDirectory()) walk(name)
      else files.push(name)
    }
  }
  walk('flowable-runtime/src/main')
  const hash = createHash('sha256')
  for (const name of files.sort()) {
    const bytes = readFileSync(path.join(root, name))
    hash.update(name)
    hash.update('\0')
    hash.update(
      /\.(java|xml|properties|json|ya?ml|txt)$/.test(name)
        ? Buffer.from(bytes.toString('utf8').replace(/\r\n/g, '\n'))
        : bytes,
    )
    hash.update('\0')
  }
  return hash.digest('hex')
}

export function writeRuntimeManifest(root, jar) {
  const value = {
    version: 1,
    sourceHash: runtimeSourceHash(root),
    jarHash: createHash('sha256').update(readFileSync(jar)).digest('hex'),
  }
  const destination = `${jar}.manifest.json`
  const temporary = `${destination}.${process.pid}.tmp`
  writeFileSync(temporary, JSON.stringify(value, null, 2))
  renameSync(temporary, destination)
}

export function runtimeManifestMatches(root, jar) {
  try {
    if (!existsSync(jar)) return false
    const value = JSON.parse(readFileSync(`${jar}.manifest.json`, 'utf8'))
    return (
      value.version === 1 &&
      value.sourceHash === runtimeSourceHash(root) &&
      value.jarHash === createHash('sha256').update(readFileSync(jar)).digest('hex')
    )
  } catch {
    return false
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  const jar = path.resolve(
    process.argv[2] || path.join(root, 'flowable-runtime/target/diagnostic-flowable-1.0.0.jar'),
  )
  writeRuntimeManifest(root, jar)
  console.log(`Runtime manifest written: ${jar}.manifest.json`)
}
