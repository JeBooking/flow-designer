<script setup lang="ts">
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const actionText = useCustomRef<string>('flowable:actionText')
</script>

<template>
  <el-collapse-item name="arg1" :title="$tu('排查动作内容')">
    <p class="action-help">
      {{ $tu('描述需要执行的机台动作；不要在此判断现象是否异常。') }}
    </p>
    <el-form-item
      :label="$tu('排查动作描述')"
      required
      :error="actionText?.trim() ? '' : $tu('此项必填')"
    >
      <el-input
        v-model="actionText"
        type="textarea"
        :rows="4"
        :placeholder="$tu('请描述需要执行的机台动作')"
      />
    </el-form-item>
  </el-collapse-item>
</template>

<style scoped lang="scss">
.action-help {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
