<script setup lang="ts">
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil.ts'
import ExecuteListener from './ExecuteListener.vue'
import ExtendedAttribute from './ExtendedProperties.vue'
import { supportsExecutionListener } from '@/views/ProcessDesigner/utils/EventDefinitionUtil.ts'
import { isIdValid } from '@/views/ProcessDesigner/utils/ValidationUtil.ts'
import { useBpmnContextService } from '@/hooks/useService.ts'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

defineOptions({
  name: 'BaseActivity',
})
const { selectedElement, updateProperties } = useBpmnContextService()
const activeTabName = ref('basic')
const actives = ref<string[]>(['general', 'arg1', 'arg2', 'arg3', 'arg4', 'pythonBinding'])
const id = useCustomRef('id')
const isExecutable = useCustomRef('isExecutable')
const name = useCustomRef('name')
// 输入过程中保留草稿，避免严格分支校验拒绝 yes/no 的中间字符。
const draftName = ref(name.value || '')
watch(name, (value) => {
  draftName.value = value || ''
})
const commitName = () => {
  name.value = draftName.value
}
const storedDetail = useCustomRef<string | undefined>('flowable:detailText')
const legacyConclusion = useCustomRef<string | undefined>('flowable:conclusionText')
const legacyAction = useCustomRef<string | undefined>('flowable:actionText')
const text = useCustomRef('text')
const propertiesByName = computed(() => {
  const businessObject = getBusinessObject(selectedElement)
  return businessObject?.$descriptor?.propertiesByName || {}
})
const showEditableName = computed(() => propertiesByName.value['name'])
const diagnosisKind = computed(() => getDiagnosisKind(selectedElement))
const detailText = computed<string>({
  get: () =>
    storedDetail.value ??
    (diagnosisKind.value === 'conclusion' ? legacyConclusion.value : legacyAction.value) ??
    '',
  set: (value) => updateProperties({ 'flowable:detailText': value }),
})
const updateId = (val: string) => {
  const msg = isIdValid(selectedElement, val)
  if (msg) {
    return ElMessage.warning(msg)
  }
  id.value = val
}
</script>

<template>
  <el-tabs v-model="activeTabName" stretch>
    <el-tab-pane :label="$t('ui.basicSettings')" name="basic">
      <el-scrollbar>
        <el-collapse v-model="actives">
          <el-collapse-item name="general" :title="$t('ui.general')">
            <el-form-item :label="$t('ui.id')">
              <el-input
                :model-value="id"
                @update:model-value="updateId"
                :placeholder="$t('ui.enterNodeId')"
              />
            </el-form-item>
            <el-form-item :label="$t('ui.name')" v-if="showEditableName">
              <el-input
                v-model="draftName"
                @change="commitName"
                :placeholder="$t('ui.enterNodeName')"
              />
            </el-form-item>
            <el-form-item :label="$t('ui.name')" v-else-if="propertiesByName['text']">
              <el-input v-model="text" :placeholder="$t('ui.enterNodeName')" />
            </el-form-item>
            <el-form-item v-if="diagnosisKind" :label="$tu('详细内容', 'Details')">
              <el-input
                v-model="detailText"
                type="textarea"
                :rows="5"
                :placeholder="$tu('请输入详细内容', 'Enter details')"
              />
            </el-form-item>
            <p v-if="diagnosisKind" class="diagnosis-help">
              {{
                $tu(
                  '名称留空时从详细内容自动生成；手动填写的名称会保留。',
                  'An empty name is generated from details; a manually entered name is preserved.',
                )
              }}
            </p>
            <el-form-item :label="$t('ui.executable')" v-if="propertiesByName['isExecutable']">
              <el-switch v-model="isExecutable" />
            </el-form-item>
            <slot name="general"></slot>
          </el-collapse-item>
          <slot name="basic"></slot>
        </el-collapse>
      </el-scrollbar>
    </el-tab-pane>
    <slot></slot>
    <el-tab-pane :label="$t('ui.otherSettings')" name="other">
      <el-scrollbar>
        <div class="other-configurations is-disabled" inert aria-disabled="true">
          <ExecuteListener v-if="supportsExecutionListener()" />
          <slot name="other"></slot>
          <ExtendedAttribute />
        </div>
      </el-scrollbar>
    </el-tab-pane>
  </el-tabs>
</template>

<style scoped lang="scss">
.diagnosis-help {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.other-configurations {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;

  &.is-disabled {
    opacity: 0.5;
    pointer-events: none;
  }
}

:deep(.el-collapse-item__header) {
  padding-left: 10px;
  box-sizing: border-box;
  position: relative;
  gap: 8px;

  &:before {
    content: '';
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    left: 0;
    width: 3px;
    height: 15px;
    background-color: var(--el-color-primary);
  }
}

:deep(.el-collapse-item__content) {
  padding: 10px 15px 0 20px;
}
</style>
