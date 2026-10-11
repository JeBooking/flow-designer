<script setup lang="ts">
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const conclusionText = useCustomRef<string>('flowable:conclusionText')
</script>

<template>
  <el-collapse-item name="arg1" :title="$tu('结论内容（必填）')">
    <p class="conclusion-help">
      {{ $tu('结论节点用于记录诊断过程中的判断，不代表最终结论。') }}
    </p>
    <p class="conclusion-help">
      {{ $tu('前序仅允许排查节点；后序必须且只能连接一项：处理动作或上升。') }}
    </p>
    <el-form-item
      :label="$tu('结论内容')"
      required
      :error="conclusionText?.trim() ? '' : $tu('此项必填')"
    >
      <el-input
        v-model="conclusionText"
        type="textarea"
        :rows="4"
        :placeholder="$tu('请描述得到的结论')"
      />
    </el-form-item>
  </el-collapse-item>
</template>

<style scoped lang="scss">
.conclusion-help {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
