import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, rm, utimes } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import {
  runtimeSourceHash,
  writeRuntimeManifest,
  runtimeManifestMatches,
} from './runtime-manifest.mjs'

const root = await mkdtemp(path.join(os.tmpdir(), 'runtime-manifest-'))
try {
  await mkdir(path.join(root, 'flowable-runtime/src/main/java'), { recursive: true })
  const source = path.join(root, 'flowable-runtime/src/main/java/Application.java')
  const jar = path.join(root, 'runtime.jar')
  await writeFile(path.join(root, 'flowable-runtime/pom.xml'), '<project />\n')
  await writeFile(source, 'class Application {}\n')
  await writeFile(jar, 'verified-runtime')
  assert.equal(runtimeManifestMatches(root, jar), false)
  writeRuntimeManifest(root, jar)
  assert.equal(runtimeManifestMatches(root, jar), true)
  const hash = runtimeSourceHash(root)
  await writeFile(source, 'class Application {}\r\n')
  await utimes(source, new Date(), new Date(Date.now() + 100000))
  assert.equal(runtimeSourceHash(root), hash)
  assert.equal(runtimeManifestMatches(root, jar), true)
  await writeFile(source, 'class Changed {}\n')
  assert.equal(runtimeManifestMatches(root, jar), false)
  writeRuntimeManifest(root, jar)
  await writeFile(jar, 'tampered-runtime')
  assert.equal(runtimeManifestMatches(root, jar), false)
  console.log(
    'PASS: prebuilt runtime source/JAR identity, copied checkout timestamps, CRLF normalization and tamper detection',
  )
} finally {
  assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()))
  await rm(root, { recursive: true, force: true })
}
