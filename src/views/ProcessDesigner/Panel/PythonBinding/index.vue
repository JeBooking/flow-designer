<script setup lang="ts">
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'
import { useBpmnContextService } from '@/hooks/useService'
import { listPythonProjects } from '@/services/pythonProjects'
import type { PythonProject } from '@/types/pythonProject'
import { useCustomRef } from '@/views/ProcessDesigner/utils/ElementUtil'

const moduleValue = useCustomRef('flowable:pythonModule')
const factoryValue = useCustomRef('flowable:pythonFactory')
const functionValue = useCustomRef('flowable:pythonFunction')
const { selectedElement, updateProperties } = useBpmnContextService()
const projects = ref<PythonProject[]>([])
const selectedProject = computed(() =>
  projects.value.find(
    (project) =>
      project.module === moduleValue.value &&
      (project.factory || '') === (factoryValue.value || ''),
  ),
)
const projectBinding = computed({
  get: () =>
    moduleValue.value ? JSON.stringify([moduleValue.value, factoryValue.value || '']) : '',
  set: (value: string) => {
    if (value === projectBinding.value) return
    const project = projects.value.find(
      (entry) => JSON.stringify([entry.module, entry.factory || '']) === value,
    )
    if (value && !project) return
    // 入口只在工程接入处配置；节点保存绑定快照，确保导出及旧流程仍能独立恢复。
    updateProperties({
      'flowable:pythonModule': project?.module || undefined,
      'flowable:pythonFactory': project?.factory || undefined,
      'flowable:pythonFunction': undefined,
      'flowable:pythonArguments': undefined,
    })
  },
})
const functionName = computed({
  get: () => functionValue.value,
  set: (value: string) =>
    updateProperties({ 'flowable:pythonFunction': value, 'flowable:pythonArguments': undefined }),
})
const isDecision = computed(() => getDiagnosisKind(selectedElement) === 'investigation')
const discoveryError = ref('')
const loadingProjects = ref(false)
const reloadProjects = async () => {
  if (loadingProjects.value) return
  loadingProjects.value = true
  discoveryError.value = ''
  try {
    projects.value = (await listPythonProjects()).projects
  } catch (error) {
    discoveryError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loadingProjects.value = false
  }
}
onMounted(reloadProjects)
const interfaces = computed(() => selectedProject.value?.interfaces || [])
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
    <el-form-item :label="$tu('Python 工程', 'Python project')">
      <el-select
        v-model="projectBinding"
        filterable
        clearable
        :loading="loadingProjects"
        :placeholder="$tu('选择已接入的工程', 'Select a registered project')"
        @visible-change="(open: boolean) => open && reloadProjects()"
      >
        <el-option
          v-if="moduleValue && !selectedProject"
          :value="projectBinding"
          :label="moduleValue + $tu('（尚未接入）', ' (not registered)')"
        />
        <el-option
          v-for="project in projects"
          :key="project.id"
          :value="JSON.stringify([project.module, project.factory || ''])"
          :label="
            project.name + ' · ' + project.module + (project.factory ? ' · ' + project.factory : '')
          "
        />
      </el-select>
    </el-form-item>
    <p v-if="moduleValue && !selectedProject && !loadingProjects">
      {{
        $tu(
          '原有接口绑定已保留。请在顶部“Python 项目”中接入对应工程，以读取接口列表。',
          'The existing binding is preserved. Register the corresponding project under Python projects to load its interfaces.',
        )
      }}
    </p>
    <el-form-item :label="$tu('调用接口', 'Interface to call')">
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
          '业务对象入口在顶部“Python 项目”中统一配置。同一次排查中，该工程的节点共享业务对象；不同排查相互隔离。参数按接口签名自动匹配，保留 Python 默认值。动作可无返回值；排查接口返回是或否。调用失败显示 Python 原生错误。',
          'Configure the business object entry once under Python projects. Nodes using that project share its business object within an investigation; separate investigations are isolated. Parameters are matched automatically, preserving Python defaults. Actions may return nothing; investigations return yes/no. Failures display native Python errors.',
        )
      }}
    </el-text>
  </el-collapse-item>
</template>
