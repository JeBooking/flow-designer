import { importWorkflowJson } from '@/views/ProcessDesigner/CodeGeneration/importWorkflow'
import { resourcePath } from '@/views/ProcessDesigner/CodeGeneration/resources'
import type { ResourceData } from '@/views/ProcessDesigner/CodeGeneration/resources'
import { translateUi } from '@/languages/uiText'
import type { ProjectFiles } from '@/views/ProcessDesigner/CodeGeneration/generate'

export interface ProjectInputFile {
  path: string
  mediaType?: string
  read: () => Promise<Uint8Array>
}

export async function importWorkflowDirectory(entries: ProjectInputFile[]) {
  const files = new Map(entries.map((entry) => [resourcePath(entry.path), entry]))
  if (files.size !== entries.length)
    throw new Error(translateUi('项目目录中存在重复路径', 'Duplicate paths in project directory'))
  const candidates = [...files.keys()]
    .filter((path) => path.split('/').slice(-1)[0] === 'workflow.json')
    .sort((a, b) => a.split('/').length - b.split('/').length)
  if (
    !candidates.length ||
    (candidates[1] && candidates[0]!.split('/').length === candidates[1].split('/').length)
  )
    throw new Error(
      translateUi(
        '请选择包含唯一 workflow.json 的项目目录',
        'Select a project directory containing a unique workflow.json',
      ),
    )
  const definition = candidates[0]!
  const base = definition.slice(0, -'workflow.json'.length)
  const content = new TextDecoder().decode(await files.get(definition)!.read())
  const resources: Record<string, ResourceData> = Object.create(null)
  const missing = new Set<string>()
  const resolve = async (path: string) => {
    path = resourcePath(path)
    if (resources[path]) return resources[path]
    const file = files.get(base + path)
    if (!file) {
      missing.add(path)
      return
    }
    return (resources[path] = { data: await file.read(), mediaType: file.mediaType })
  }
  const restored = await importWorkflowJson(content, resolve)
  // 清单不限定资源类型，文档、视频或数据文件与图片使用同一目录引用规则。
  const metadata = JSON.parse(content.replace(/^\uFEFF/, '')) as {
    resources?: { path: string; mediaType?: string }[]
  }
  for (const resource of metadata.resources || []) {
    const value = await resolve(resource.path)
    if (value && resource.mediaType) value.mediaType = resource.mediaType
  }
  return { ...restored, resources, missingResources: [...missing] }
}

export function supplyProjectResources(
  files: ProjectFiles,
  available: Record<string, ResourceData>,
) {
  const definition = JSON.parse(files['workflow.json'] as string) as {
    resources?: { path: string }[]
  }
  for (const resource of definition.resources || []) {
    const path = resourcePath(resource.path)
    if (Object.prototype.hasOwnProperty.call(files, path)) {
      if (typeof files[path] === 'string')
        throw new Error(
          translateUi('资源路径与项目文件冲突：', 'Resource path conflicts with a project file: ') +
            path,
        )
      continue
    }
    const value = available[path]
    if (!value)
      throw new Error(
        translateUi(
          '资源未加载，请从项目目录导入后再导出：',
          'Resource is not loaded. Import the project directory before exporting: ',
        ) + path,
      )
    files[path] = value.data
  }
  return files
}
