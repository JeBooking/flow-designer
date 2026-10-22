<script setup lang="ts">
import type EventBus from 'diagram-js/lib/core/EventBus'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { useBpmnContextService } from '@/hooks/useService'
import type { InvestigationData } from '@/types/diagnosis'
import {
  diagnosisKinds,
  getDiagnosisKind,
  isReferenceImage,
} from '@/views/ProcessDesigner/Diagnosis/model'
import { customTranslate } from '@/views/ProcessDesigner/Translate'
import { translateUi } from '@/languages/uiText'

const { selectedElement, getService, updateProperties } = useBpmnContextService()
const eventBus = getService<EventBus>('eventBus')!
const revision = ref(0)
const kind = getDiagnosisKind(selectedElement)!
const data = computed<InvestigationData>(() => {
  void revision.value
  const businessObject = getBusinessObject(selectedElement)
  return {
    observation: businessObject.get('flowable:observation') || '',
    acquisition: businessObject.get('flowable:acquisition') || '',
    referenceImage: businessObject.get('flowable:referenceImage') || '',
    assessment: businessObject.get('flowable:assessment') || '',
  }
})
const refresh = () => {
  revision.value++
}
eventBus.on('elements.changed', refresh)
let disposed = false
onBeforeUnmount(() => {
  disposed = true
  eventBus.off('elements.changed', refresh)
})
const update = (field: keyof InvestigationData, value: string) => {
  updateProperties({ [`flowable:${field}`]: value || undefined })
}
const notifyImageError = (message: string) => {
  ElNotification.error({
    title: translateUi('参考图处理失败', 'Reference image processing failed'),
    message,
    duration: 0,
  })
}
const imageFileDetails = (file: File) =>
  `${translateUi('文件', 'File')}: ${file.name} (${file.size} ${translateUi('字节', 'bytes')}, MIME ${file.type || translateUi('未识别', 'unrecognized')})`
const describeImageError = (error: unknown) => {
  if (error instanceof DOMException || error instanceof Error) {
    return `${error.name}: ${error.message || translateUi('浏览器未提供错误详情', 'The browser provided no error details')}`
  }
  return String(
    error || translateUi('浏览器未提供错误详情', 'The browser provided no error details'),
  )
}
const formatImageFailure = (stage: string, stageEnglish: string, reason: string, file: File) =>
  [
    `${translateUi('失败阶段', 'Failed at')}: ${translateUi(stage, stageEnglish)}`,
    `${translateUi('具体错误', 'Error details')}: ${reason}`,
    imageFileDetails(file),
    translateUi(
      '网络状态：没有发起上传请求；文件由浏览器本地读取并保存。',
      'Network: no upload request was made; the file is read and saved locally by the browser.',
    ),
  ].join('；')
const fields: { key: 'observation' | 'acquisition' | 'assessment'; label: string; hint: string }[] =
  [
    { key: 'observation', label: '查看什么数据', hint: '写明数据名称、测点、单位和观察范围' },
    { key: 'acquisition', label: '如何获取数据', hint: '写明工具、操作步骤、采集条件和注意事项' },
    { key: 'assessment', label: '如何判断问题', hint: '写明正常范围、异常判据及如何对照参考图' },
  ]
const uploading = ref(false)
const uploadImage = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    notifyImageError(
      formatImageFailure(
        '文件检查',
        'File validation',
        translateUi('图片超过 5 MB 限制', 'The image exceeds the 5 MB limit'),
        file,
      ),
    )
    return
  }
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
    notifyImageError(
      formatImageFailure(
        '文件检查',
        'File validation',
        translateUi(
          '不支持此图片类型；允许 PNG、JPEG 或 WebP',
          'Unsupported image type; PNG, JPEG or WebP is required',
        ),
        file,
      ),
    )
    return
  }
  uploading.value = true
  let stage: '本地读取' | '图片解码' | '写入流程模型' = '本地读取'
  try {
    const value = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () =>
        reject(reader.error || new Error('FileReader failed without browser error details'))
      reader.onabort = () => reject(new DOMException('File reading was aborted', 'AbortError'))
      reader.readAsDataURL(file)
    })
    stage = '图片解码'
    const image = new Image()
    image.src = value
    await image.decode()
    // 读取文件期间可能切换节点，不能把图片写入新选中的节点。
    if (!disposed && useBpmnContextService().selectedElement === selectedElement) {
      stage = '写入流程模型'
      update('referenceImage', value)
    }
  } catch (error) {
    if (!disposed) {
      const stageDetails = {
        本地读取: 'Local file read',
        图片解码: 'Image decoding',
        写入流程模型: 'Saving to the process model',
      } as const
      notifyImageError(
        formatImageFailure(stage, stageDetails[stage], describeImageError(error), file),
      )
    }
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-collapse-item name="arg1" :title="customTranslate(diagnosisKinds[kind].label)">
    <template v-if="kind === 'investigation'">
      <p class="diagnosis-help">{{ $tu('需要继续排查') }}</p>
      <p class="diagnosis-help">
        {{
          $tu(
            '前序仅允许开始事件、排查节点或排查动作；后序仅允许排查节点、排查动作、结论、处理动作或上升。',
          )
        }}
      </p>
      <el-form-item
        v-for="field in fields.slice(0, 2)"
        :key="field.key"
        :label="$tu(field.label)"
        required
        :error="data[field.key].trim() ? '' : $tu('此项必填')"
      >
        <el-input
          :model-value="data[field.key]"
          type="textarea"
          :rows="3"
          :placeholder="$tu(field.hint)"
          @update:model-value="(value: string) => update(field.key, value)"
        />
      </el-form-item>
      <el-form-item
        :label="$tu('排查参考图')"
        required
        :error="isReferenceImage(data.referenceImage) ? '' : $tu('请上传有效参考图')"
      >
        <div class="reference-image">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            :disabled="uploading"
            :aria-label="$tu('排查参考图')"
            @change="uploadImage"
          />
          <span>
            {{
              $tu(
                '图片在浏览器本地读取并保存到流程，无需网络；支持 PNG、JPEG、WebP，最大 5 MB。若文件选择窗口被浏览器或系统策略拦截，页面可能收不到事件，因此无法显示具体拦截原因。',
                'Images are read locally and saved in the process; no network is used. PNG, JPEG or WebP, up to 5 MB. If the browser or system blocks the file picker, the page may receive no event and cannot report the specific reason.',
              )
            }}
          </span>
          <template v-if="isReferenceImage(data.referenceImage)">
            <el-image
              :src="data.referenceImage"
              :preview-src-list="[data.referenceImage]"
              fit="contain"
              :alt="$tu('排查参考图')"
            />
            <el-button @click="update('referenceImage', '')">{{ $tu('移除参考图') }}</el-button>
          </template>
        </div>
      </el-form-item>
      <el-form-item
        :label="$tu(fields[2]!.label)"
        required
        :error="data.assessment.trim() ? '' : $tu('此项必填')"
      >
        <el-input
          :model-value="data.assessment"
          type="textarea"
          :rows="4"
          :placeholder="$tu(fields[2]!.hint)"
          @update:model-value="(value: string) => update('assessment', value)"
        />
      </el-form-item>
    </template>
    <p v-else class="diagnosis-help">{{ $tu('占位节点：当前仅用于验证诊断流程的连接规则。') }}</p>
  </el-collapse-item>
</template>

<style scoped lang="scss">
.diagnosis-help {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.reference-image {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
  width: 100%;
  input {
    max-width: 100%;
  }
  span {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }
  .el-image {
    width: 100%;
    height: 160px;
  }
}
</style>
