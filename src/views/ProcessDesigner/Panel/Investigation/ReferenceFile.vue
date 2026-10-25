<script setup lang="ts">
import {
  MAX_REFERENCE_FILE_BYTES,
  parseReferenceFile,
} from '@/views/ProcessDesigner/Diagnosis/model'
import { openReferenceFile } from '@/services/referenceFiles'
import { translateUi } from '@/languages/uiText'
import { resourceExtension } from '@/views/ProcessDesigner/CodeGeneration/resources'

const props = defineProps<{ value: string; name?: string; readonly?: boolean }>()
const emit = defineEmits<{ change: [value: string, name: string] }>()
const busy = ref(false)
const error = ref('')
const preview = ref(false)
const resource = computed(() => parseReferenceFile(props.value))
const filename = computed(
  () => props.name || `reference.${resourceExtension(resource.value?.mediaType)}`,
)
// 只嵌入浏览器可安全处理的静态类型；HTML/SVG/XML 等活动文档交给本机软件。
const previewKind = computed(() => {
  const type = resource.value?.mediaType || ''
  if (/^image\/(png|jpeg|webp|gif|bmp|avif|x-icon)$/.test(type)) return 'image'
  if (type === 'application/pdf') return 'pdf'
  if (
    ['text/plain', 'text/csv', 'text/markdown', 'application/json', 'application/log'].includes(
      type,
    )
  )
    return 'text'
  if (/^audio\/(mpeg|mp3|ogg|wav|x-wav|webm|mp4|aac|flac)$/.test(type)) return 'audio'
  if (/^video\/(mp4|webm|ogg|quicktime)$/.test(type)) return 'video'
  return ''
})
const textContent = computed(() => {
  if (previewKind.value !== 'text' || !resource.value) return ''
  const bytes = Uint8Array.from(atob(resource.value.base64), (character) => character.charCodeAt(0))
  return new TextDecoder().decode(bytes)
})
const objectUrl = ref('')
watch(
  () => props.value,
  () => {
    if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
    objectUrl.value = ''
    preview.value = false
    error.value = ''
    if (resource.value) {
      const bytes = Uint8Array.from(atob(resource.value.base64), (character) =>
        character.charCodeAt(0),
      )
      objectUrl.value = URL.createObjectURL(new Blob([bytes], { type: resource.value.mediaType }))
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  if (objectUrl.value) URL.revokeObjectURL(objectUrl.value)
})
let disposed = false
onBeforeUnmount(() => {
  disposed = true
})
const inferredType = (file: File) => {
  const known: Record<string, string> = {
    txt: 'text/plain',
    log: 'text/plain',
    csv: 'text/csv',
    md: 'text/markdown',
    json: 'application/json',
    pdf: 'application/pdf',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    gif: 'image/gif',
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    mp4: 'video/mp4',
    webm: 'video/webm',
    ogg: 'audio/ogg',
  }
  return (
    file.type ||
    known[file.name.split('.').pop()?.toLowerCase() || ''] ||
    'application/octet-stream'
  )
}
const upload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  error.value = ''
  if (file.size > MAX_REFERENCE_FILE_BYTES) {
    error.value = translateUi('文件超过 50 MB 限制', 'The file exceeds the 50 MB limit')
    return
  }
  busy.value = true
  try {
    const buffer = await file.arrayBuffer()
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let offset = 0; offset < bytes.length; offset += 8192) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192))
    }
    const value = `data:${inferredType(file)};base64,${btoa(binary)}`
    if (!parseReferenceFile(value))
      throw new Error(translateUi('文件类型或内容无效', 'Invalid file type or content'))
    if (!disposed) emit('change', value, file.name)
  } catch (failure) {
    if (!disposed)
      error.value =
        translateUi('读取参考文件失败：', 'Failed to read the reference file: ') + String(failure)
  } finally {
    busy.value = false
  }
}
const openLocal = async () => {
  error.value = ''
  busy.value = true
  try {
    await openReferenceFile(filename.value, props.value)
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : String(failure)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="reference-file">
    <input
      v-if="!readonly"
      type="file"
      :disabled="busy"
      :aria-label="$tu('参考文件', 'Reference file')"
      @change="upload"
    />
    <p v-if="!readonly" class="reference-help">
      {{
        $tu(
          '支持任意类型文件，最大 50 MB；文件在浏览器本地读取。',
          'Any file type, up to 50 MB. Files are read locally in your browser.',
        )
      }}
    </p>
    <template v-if="resource">
      <span class="reference-name">{{ filename }}</span>
      <div class="reference-actions">
        <el-button v-if="previewKind" :disabled="busy" @click="preview = !preview">{{
          preview ? $tu('收起预览', 'Hide preview') : $tu('预览文件', 'Preview file')
        }}</el-button>
        <el-button :loading="busy" @click="openLocal">{{
          $tu('用本机软件打开', 'Open with local application')
        }}</el-button>
        <el-button v-if="!readonly" :disabled="busy" @click="emit('change', '', '')">{{
          $tu('移除参考文件', 'Remove reference file')
        }}</el-button>
      </div>
      <p class="reference-help">
        {{
          $tu(
            '本机打开需要启动 Python 服务；无关联软件时显示系统“打开方式”。脚本和快捷方式始终选择查看软件。',
            'Opening locally requires the Python service. Unassociated files show the system app chooser. Scripts and shortcuts always ask for a viewing application.',
          )
        }}
      </p>
      <template v-if="preview">
        <el-image
          v-if="previewKind === 'image'"
          :src="objectUrl"
          :preview-src-list="[objectUrl]"
          fit="contain"
          :alt="$tu('参考文件', 'Reference file')"
        />
        <iframe
          v-else-if="previewKind === 'pdf'"
          :src="objectUrl"
          :title="$tu('参考文件预览', 'Reference file preview')"
        />
        <pre v-else-if="previewKind === 'text'" tabindex="0">{{ textContent }}</pre>
        <audio v-else-if="previewKind === 'audio'" :src="objectUrl" controls preload="metadata" />
        <video v-else-if="previewKind === 'video'" :src="objectUrl" controls preload="metadata" />
      </template>
    </template>
    <p v-if="error" class="reference-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped lang="scss">
.reference-file {
  width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reference-file input,
.reference-file audio,
.reference-file video {
  max-width: 100%;
}
.reference-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.reference-actions .el-button {
  margin-left: 0;
}
.reference-help {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}
.reference-name {
  overflow-wrap: anywhere;
}
.reference-error {
  margin: 0;
  color: var(--el-color-danger);
  overflow-wrap: anywhere;
}
.reference-file .el-image {
  width: 100%;
  height: 180px;
}
.reference-file iframe {
  width: 100%;
  height: 400px;
  border: 1px solid var(--el-border-color);
}
.reference-file pre {
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  padding: 12px;
  background: var(--el-fill-color-light);
}
</style>
