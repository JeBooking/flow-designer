<script setup lang="ts">
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const moduleName = useCustomRef('flowable:pythonModule')
const functionName = useCustomRef('flowable:pythonFunction')
const argumentsJson = useCustomRef('flowable:pythonArguments')
const topic = useCustomRef('flowable:pythonTopic')
const argumentError = computed(() => {
  try {
    const parsed: unknown = JSON.parse(argumentsJson.value || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error()
    return ''
  } catch {
    return translateUi('参数必须是 JSON 对象', 'Arguments must be a JSON object')
  }
})
</script>

<template>
  <el-collapse-item
    name="pythonBinding"
    :title="$tu('Python 外部接口', 'External Python interface')"
  >
    <el-form-item :label="$tu('模块路径', 'Module path')">
      <el-input v-model="moduleName" placeholder="diagnostic_demo.api" />
    </el-form-item>
    <el-form-item :label="$tu('函数名称', 'Function name')">
      <el-input v-model="functionName" placeholder="inspect_temperature" />
    </el-form-item>
    <el-form-item :label="$tu('工作主题', 'Job topic')">
      <el-input v-model="topic" :placeholder="$tu('留空使用节点 ID', 'Defaults to the node ID')" />
    </el-form-item>
    <el-form-item :label="$tu('关键字参数', 'Keyword arguments')" :error="argumentError">
      <el-input
        v-model="argumentsJson"
        type="textarea"
        :rows="5"
        placeholder='{"data": "$Inspect.data"}'
      />
    </el-form-item>
    <el-text size="small" type="info">
      {{
        $tu(
          '以 $ 开头的参数读取流程变量。分支函数返回 next，值为后继连线 ID。',
          'Arguments starting with $ read process variables. Branch functions return next with an outgoing flow ID.',
        )
      }}
    </el-text>
  </el-collapse-item>
</template>
