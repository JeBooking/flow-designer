<script setup lang="ts">
import type EventBus from 'diagram-js/lib/core/EventBus'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { useBpmnContextService } from '@/hooks/useService'
import type { InvestigationData } from '@/types/diagnosis'
import {
  diagnosisKinds,
  getDiagnosisKind,
  isReferenceFile,
} from '@/views/ProcessDesigner/Diagnosis/model'
import { customTranslate } from '@/views/ProcessDesigner/Translate'
import ReferenceFile from '@/views/ProcessDesigner/Panel/Investigation/ReferenceFile.vue'

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
    referenceImageName: businessObject.get('flowable:referenceImageName') || '',
    assessment: businessObject.get('flowable:assessment') || '',
  }
})
const refresh = () => {
  revision.value++
}
eventBus.on('elements.changed', refresh)
onBeforeUnmount(() => {
  eventBus.off('elements.changed', refresh)
})
const update = (field: keyof InvestigationData, value: string) => {
  updateProperties({ [`flowable:${field}`]: value || undefined })
}
const updateReferenceFile = (value: string, name: string) => {
  if (useBpmnContextService().selectedElement !== selectedElement) return
  updateProperties({
    'flowable:referenceImage': value || undefined,
    'flowable:referenceImageName': name || undefined,
    'flowable:referenceImagePath': undefined,
  })
}
const fields: { key: 'observation' | 'acquisition' | 'assessment'; label: string; hint: string }[] =
  [
    { key: 'observation', label: '查看什么数据', hint: '写明数据名称、测点、单位和观察范围' },
    { key: 'acquisition', label: '如何获取数据', hint: '写明工具、操作步骤、采集条件和注意事项' },
    { key: 'assessment', label: '如何判断问题', hint: '写明正常范围、异常判据及如何对照参考文件' },
  ]
</script>

<template>
  <el-collapse-item name="arg1" :title="customTranslate(diagnosisKinds[kind].label)">
    <template v-if="kind === 'investigation'">
      <p class="diagnosis-help">{{ $tu('需要继续排查') }}</p>
      <p class="diagnosis-help">
        {{
          $tu(
            '前序仅允许开始事件、排查节点或排查动作；后序仅允许排查节点、排查动作、结论或上升。',
            'Predecessors: start, investigation or investigation action. Successors: investigation, investigation action, conclusion or escalation.',
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
        :label="$tu('参考文件', 'Reference file')"
        required
        :error="
          isReferenceFile(data.referenceImage)
            ? ''
            : $tu('请添加有效参考文件', 'Add a valid reference file')
        "
      >
        <ReferenceFile
          :value="data.referenceImage"
          :name="data.referenceImageName"
          @change="updateReferenceFile"
        />
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
</style>
