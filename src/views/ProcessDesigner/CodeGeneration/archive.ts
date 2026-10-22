import type { ProjectFiles } from '@/views/ProcessDesigner/CodeGeneration/generate'

// 使用 ZIP 的存储模式，无压缩依赖；CRC 保证解压工具可校验每个文件。
export function createArchive(files: ProjectFiles): Blob {
  const encoder = new TextEncoder()
  const local: Uint8Array<ArrayBuffer>[] = []
  const central: Uint8Array<ArrayBuffer>[] = []
  let offset = 0
  for (const [path, value] of Object.entries(files)) {
    const name = encoder.encode(path)
    const data = typeof value === 'string' ? encoder.encode(value) : new Uint8Array(value)
    let crc = 0xffffffff
    for (const byte of data) {
      crc ^= byte
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
    }
    crc = (crc ^ 0xffffffff) >>> 0
    const header = new Uint8Array(30 + name.length)
    const view = new DataView(header.buffer)
    view.setUint32(0, 0x04034b50, true)
    view.setUint16(4, 20, true)
    view.setUint16(6, 0x800, true)
    view.setUint16(12, 33, true)
    view.setUint32(14, crc, true)
    view.setUint32(18, data.length, true)
    view.setUint32(22, data.length, true)
    view.setUint16(26, name.length, true)
    header.set(name, 30)
    const directory = new Uint8Array(46 + name.length)
    const entry = new DataView(directory.buffer)
    entry.setUint32(0, 0x02014b50, true)
    entry.setUint16(4, 20, true)
    directory.set(header.subarray(4, 30), 6)
    entry.setUint32(42, offset, true)
    directory.set(name, 46)
    local.push(header, data)
    central.push(directory)
    offset += header.length + data.length
  }
  const directorySize = central.reduce((size, chunk) => size + chunk.length, 0)
  const end = new Uint8Array(22)
  const view = new DataView(end.buffer)
  view.setUint32(0, 0x06054b50, true)
  view.setUint16(8, central.length, true)
  view.setUint16(10, central.length, true)
  view.setUint32(12, directorySize, true)
  view.setUint32(16, offset, true)
  return new Blob([...local, ...central, end], { type: 'application/zip' })
}
