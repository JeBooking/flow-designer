import { translateUi } from '@/languages/uiText'

export interface WorkflowResource {
  path: string
  mediaType?: string
}
export interface ResourceData {
  data: Uint8Array
  mediaType?: string
}
export type ResourceResolver = (path: string) => Promise<ResourceData | undefined>

/** 资源路径相对于 workflow.json 所在目录，项目移动后仍然有效。 */
export function resourcePath(value: string): string {
  const path = value.replace(/\\/g, '/').replace(/^\.\//, '')
  if (
    !path ||
    path.startsWith('/') ||
    /[:\u0000-\u001f]/.test(path) ||
    path.split('/').some((part) => !part || part === '.' || part === '..')
  )
    throw new Error(
      translateUi('资源必须使用项目内相对路径：', 'Resources require a project-relative path: ') +
        value,
    )
  return path
}

export function decodeResource(value: string): ResourceData | undefined {
  const match = /^data:([\w.+/-]+);base64,([A-Za-z0-9+/]*={0,2})$/.exec(value)
  if (!match) return
  return {
    mediaType: match[1],
    data: Uint8Array.from(atob(match[2]!), (character) => character.charCodeAt(0)),
  }
}

// Base64 仅用于现有画布预览适配；项目 JSON 和磁盘资源始终分离保存。
export function resourceDataUrl(resource: ResourceData): string {
  let text = ''
  for (let index = 0; index < resource.data.length; index += 8192)
    text += String.fromCharCode(...resource.data.subarray(index, index + 8192))
  return `data:${resource.mediaType || 'application/octet-stream'};base64,${btoa(text)}`
}

export function resourceExtension(mediaType?: string): string {
  const extensions: Record<string, string> = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'application/pdf': 'pdf',
    'text/plain': 'txt',
    'video/mp4': 'mp4',
    'audio/mpeg': 'mp3',
    'application/json': 'json',
  }
  return extensions[mediaType || ''] || 'bin'
}
