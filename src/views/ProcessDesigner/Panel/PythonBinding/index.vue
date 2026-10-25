<script setup lang="ts">
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'
import { useBpmnContextService } from '@/hooks/useService'
import { listPythonProjects } from '@/services/pythonProjects'
import type { PythonProject } from '@/types/pythonProject'
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const moduleValue = useCustomRef('flowable:pythonModule')
const functionValue = useCustomRef('flowable:pythonFunction')
const { selectedElement, updateProperties } = useBpmnContextService()
const moduleName = computed({
  get: () => moduleValue.value,
  set: (value: string) =>
    updateProperties({
      'flowable:pythonModule': value,
      'flowable:pythonFunction': undefined,
      'flowable:pythonArguments': undefined,
    }),
})
const functionName = computed({
  get: () => functionValue.value,
  set: (value: string) =>
    updateProperties({ 'flowable:pythonFunction': value, 'flowable:pythonArguments': undefined }),
})
const isDecision = computed(() => getDiagnosisKind(selectedElement) === 'investigation')
const projects = ref<PythonProject[]>([])
const discoveryError = ref('')
onMounted(async () => {
  try {
    projects.value = (await listPythonProjects()).projects
  } catch (error) {
    discoveryError.value = error instanceof Error ? error.message : String(error)
  }
})
const interfaces = computed(() =>
  projects.value
    .filter((project) => project.module === moduleName.value)
    .flatMap((project) => project.interfaces),
)
const topic = useCustomRef('flowable:pythonTopic')
const humanDecision = useCustomRef<boolean>('flowable:humanDecision')
</script>

<template>
  <el-collapse-item
    name="pythonBinding"
    :title="
      isDecision
        ? $tu('执行与人工判断', 'Execution and human decisions')
        : $tu('接口绑定', 'Interface binding')
    "
  >
    <p v-if="isDecision">
      {{
        $tu(
          '判断组件未实现业务逻辑时会自动请求人工判断，无需开启下方开关。下方开关用于额外要求人工复核。',
          'Decision components automatically request human judgment when their business logic is unimplemented. The switch below additionally requires human review.',
        )
      }}
    </p>
    <el-form-item v-if="isDecision" :label="$tu('人工判断／确认', 'Human decision / confirmation')">
      <el-switch
        v-model="humanDecision"
        :aria-label="$tu('人工判断／确认', 'Human decision / confirmation')"
      />
    </el-form-item>
    <p v-if="isDecision && humanDecision">
      {{
        $tu(
          '运行到此节点后等待人工选择，可继续或回退到此前执行过的节点。Python 接口可留空；配置后先运行接口，再等待人工确认。',
          'Wait here for a human to continue or return to an earlier node. Python is optional; when configured, it runs before the human decision.',
        )
      }}
    </p>
    <el-form-item :label="$tu('模块路径', 'Module path')">
      <el-select v-model="moduleName" filterable allow-create default-first-option>
        <el-option
          v-for="project in projects"
          :key="project.id"
          :value="project.module"
          :label="project.name + ' · ' + project.module"
        />
      </el-select>
    </el-form-item>
    <el-form-item :label="$tu('函数名称', 'Function name')">
      <el-select v-model="functionName" filterable allow-create default-first-option>
        <el-option
          v-for="api in interfaces"
          :key="api.name"
          :value="api.name"
          :label="api.name + api.signature"
        />
      </el-select>
    </el-form-item>
    <el-form-item :label="$tu('工作主题', 'Job topic')">
      <el-input v-model="topic" :placeholder="$tu('留空使用节点 ID', 'Defaults to the node ID')" />
    </el-form-item>
    <p v-if="discoveryError" role="status">{{ discoveryError }}</p>
    <el-text size="small" type="info">
      {{
        $tu(
          '参数按接口签名自动匹配流程变量或上游结果中的同名字段，默认值自动保留，无参数接口直接调用。动作可无返回值；排查接口返回是或否。数据缺失或同名冲突时会提示具体参数，不需要填写代码。',
          'Parameters are matched by name from workflow variables or upstream results, preserving defaults. No-argument and void actions are supported. Investigations return yes/no. Missing or ambiguous data reports the parameter; no code entry is needed.',
        )
      }}
    </el-text>
  </el-collapse-item>
</template>
