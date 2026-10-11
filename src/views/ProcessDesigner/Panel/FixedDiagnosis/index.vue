<script setup lang="ts">
import { useBpmnContextService } from '@/hooks/useService'
import {
  diagnosisNodeName,
  getDiagnosisKind,
  isFixedDiagnosisNode,
} from '@/views/ProcessDesigner/Diagnosis/model'

const { selectedElement, updateProperties } = useBpmnContextService()
const kind = computed(() => getDiagnosisKind(selectedElement))
const fixedName = computed(() => (kind.value ? diagnosisNodeName(kind.value, (key) => key) : ''))
const currentName = computed(() => selectedElement?.businessObject?.get('name') || '')
const repairName = () => updateProperties({ name: fixedName.value })
</script>

<template>
  <el-collapse-item
    v-if="isFixedDiagnosisNode(selectedElement)"
    name="arg1"
    :title="$tu('固定节点内容')"
  >
    <p>{{ fixedName }}</p>
    <el-button v-if="currentName !== fixedName" type="primary" link @click="repairName">
      {{ $tu('修正为固定内容') }}
    </el-button>
  </el-collapse-item>
</template>
