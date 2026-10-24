<script setup lang="ts">
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const moduleName = useCustomRef('flowable:pythonModule')
const functionName = useCustomRef('flowable:pythonFunction')
const argumentsJson = useCustomRef('flowable:pythonArguments')
const topic = useCustomRef('flowable:pythonTopic')
const humanDecision = useCustomRef<boolean>('flowable:humanDecision')
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
    :title="$tu('执行与人工判断', 'Execution and human decisions')"
  >
    <p>
      {{
        $tu(
          '判断组件未实现业务逻辑时会自动请求人工判断，无需开启下方开关。下方开关用于额外要求人工复核。',
          'Decision components automatically request human judgment when their business logic is unimplemented. The switch below additionally requires human review.',
        )
      }}
    </p>
    <el-form-item :label="$tu('人工判断／确认', 'Human decision / confirmation')">
      <el-switch
        v-model="humanDecision"
        :aria-label="$tu('人工判断／确认', 'Human decision / confirmation')"
      />
    </el-form-item>
    <p v-if="humanDecision">
      {{
        $tu(
          '运行到此节点后等待人工选择，可继续或回退到此前执行过的节点。Python 接口可留空；配置后先运行接口，再等待人工确认。',
          'Wait here for a human to continue or return to an earlier node. Python is optional; when configured, it runs before the human decision.',
        )
      }}
    </p>
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
          '以 $ 开头的参数读取流程变量。自动分支函数返回 next，值为后继连线 ID；人工模式由用户选择分支。',
          'Arguments starting with $ read process variables. Automatic branches return next with an outgoing flow ID; human mode uses the selected option.',
        )
      }}
    </el-text>
  </el-collapse-item>
</template>
