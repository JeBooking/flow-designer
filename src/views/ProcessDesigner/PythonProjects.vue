<script setup lang="ts">
import type {
  PythonProject,
  PythonProjectRegistration,
  PythonInterface,
} from '@/types/pythonProject'
import {
  listPythonProjects,
  registerPythonProject,
  refreshPythonProject,
  removePythonProject,
  callPythonInterface,
} from '@/services/pythonProjects'

const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const projects = ref<PythonProject[]>([])
const selectedId = ref('')
const selected = computed(() => projects.value.find((p) => p.id === selectedId.value))
const registration = reactive<PythonProjectRegistration>({
  name: '',
  path: '',
  module: '',
  python: '',
})
const error = ref('')
const activeFunction = ref<PythonInterface>()
const positional = ref('[]')
const keywords = ref('{}')
const output = ref('')
const resetSelection = () => {
  activeFunction.value = undefined
  output.value = ''
}
const describe = (failure: unknown) =>
  failure instanceof Error ? failure.message : String(failure)
const load = async () => {
  loading.value = true
  error.value = ''
  try {
    projects.value = (await listPythonProjects()).projects
    if (!projects.value.some((p) => p.id === selectedId.value))
      selectedId.value = projects.value[0]?.id || ''
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    loading.value = false
  }
}
const open = () => {
  visible.value = true
  void load()
}
defineExpose({ open })
const register = async () => {
  if (!registration.path.trim() || !registration.module.trim()) {
    error.value = translateUi(
      '请填写项目目录和入口模块',
      'Enter the project directory and entry module',
    )
    return
  }
  busy.value = true
  error.value = ''
  try {
    const { project } = await registerPythonProject({ ...registration })
    selectedId.value = project.id
    activeFunction.value = undefined
    await load()
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const refresh = async () => {
  if (!selected.value) return
  busy.value = true
  error.value = ''
  try {
    await refreshPythonProject(selected.value.id)
    activeFunction.value = undefined
    await load()
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const remove = async () => {
  if (!selected.value) return
  busy.value = true
  error.value = ''
  try {
    await removePythonProject(selected.value.id)
    activeFunction.value = undefined
    await load()
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const choose = (entry: PythonInterface) => {
  activeFunction.value = entry
  output.value = ''
  positional.value = '[]'
  keywords.value = '{}'
}
const call = async () => {
  if (!selected.value || !activeFunction.value) return
  busy.value = true
  error.value = ''
  output.value = ''
  try {
    const args: unknown = JSON.parse(positional.value)
    const kwargs: unknown = JSON.parse(keywords.value)
    if (!Array.isArray(args) || !kwargs || typeof kwargs !== 'object' || Array.isArray(kwargs)) {
      throw new Error(
        translateUi(
          '位置参数须为 JSON 数组，关键字参数须为 JSON 对象',
          'Positional arguments must be a JSON array; keyword arguments must be a JSON object',
        ),
      )
    }
    const result = await callPythonInterface(
      selected.value.id,
      activeFunction.value.name,
      args,
      kwargs as Record<string, unknown>,
    )
    output.value = JSON.stringify(result, null, 2)
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const example = () => {
  Object.assign(registration, {
    name: 'sample_plot',
    path: 'backend/examples/sample_project',
    module: 'sample_plot',
    python: '',
  })
}
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="$tu('Python 项目接入', 'Python project integration')"
    size="min(760px, 100vw)"
  >
    <p>
      {{
        $tu(
          '先运行 python backend/server.py。目录指 Python 后端所在电脑上的目录，接入不会复制或修改外部工程。',
          'Start python backend/server.py first. Paths refer to the backend computer; registration does not copy or modify the project.',
        )
      }}
    </p>
    <el-form label-position="top" :disabled="busy">
      <el-form-item :label="$tu('项目名称（可选）', 'Project name (optional)')"
        ><el-input v-model="registration.name"
      /></el-form-item>
      <el-form-item :label="$tu('项目目录', 'Project directory')" required
        ><el-input v-model="registration.path" placeholder="D:\projects\plotting"
      /></el-form-item>
      <el-form-item :label="$tu('入口模块', 'Entry module')" required
        ><el-input v-model="registration.module" placeholder="plotting.api"
      /></el-form-item>
      <el-form-item
        :label="
          $tu(
            'Python 解释器（留空使用后端环境）',
            'Python executable (blank uses backend environment)',
          )
        "
        ><el-input
          v-model="registration.python"
          placeholder="D:\projects\plotting\.venv\Scripts\python.exe"
      /></el-form-item>
      <el-space wrap>
        <el-button type="primary" :loading="busy" @click="register">{{
          $tu('接入项目', 'Register project')
        }}</el-button>
        <el-button @click="example">{{ $tu('填入示例项目', 'Use example project') }}</el-button>
      </el-space>
    </el-form>
    <el-divider />
    <el-form label-position="top" :disabled="busy || loading">
      <el-form-item :label="$tu('已接入项目', 'Registered projects')">
        <el-select v-model="selectedId" @change="resetSelection" style="width: 100%">
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="`${project.name} (${project.module})`"
            :value="project.id"
          />
        </el-select>
      </el-form-item>
      <el-space wrap>
        <el-button :loading="loading" @click="load">{{
          $tu('刷新项目列表', 'Reload projects')
        }}</el-button>
        <el-button :disabled="!selected" @click="refresh">{{
          $tu('重新读取接口', 'Reload interfaces')
        }}</el-button>
        <el-button :disabled="!selected" @click="remove">{{
          $tu('移除接入（保留文件）', 'Unregister (keep files)')
        }}</el-button>
      </el-space>
    </el-form>
    <template v-if="selected">
      <p class="module-path">{{ selected.moduleFile }}</p>
      <p v-if="!selected.interfaces.length">
        {{
          $tu(
            '入口没有公开函数。请用 __all__ 导出函数，或在入口模块中定义公开函数。',
            'No public functions. Export functions through __all__, or define public functions in the entry module.',
          )
        }}
      </p>
      <el-table :data="selected.interfaces">
        <el-table-column :label="$tu('函数接口', 'Function')">
          <template #default="{ row }"
            ><code>{{ row.name }}{{ row.signature }}</code>
            <p>{{ row.description }}</p></template
          >
        </el-table-column>
        <el-table-column width="100"
          ><template #default="{ row }"
            ><el-button :disabled="busy" @click="choose(row)">{{
              $tu('选择', 'Select')
            }}</el-button></template
          ></el-table-column
        >
      </el-table>
    </template>
    <el-form v-if="activeFunction" label-position="top" :disabled="busy">
      <h3>{{ activeFunction.name }}{{ activeFunction.signature }}</h3>
      <el-form-item :label="$tu('位置参数（JSON 数组）', 'Positional arguments (JSON array)')"
        ><el-input v-model="positional" type="textarea" :rows="3"
      /></el-form-item>
      <el-form-item :label="$tu('关键字参数（JSON 对象）', 'Keyword arguments (JSON object)')"
        ><el-input v-model="keywords" type="textarea" :rows="3"
      /></el-form-item>
      <el-button type="primary" :loading="busy" @click="call">{{
        $tu('调用 Python 接口', 'Call Python function')
      }}</el-button>
    </el-form>
    <div v-if="error" role="alert" class="error-output">
      <h3>{{ $tu('操作未完成', 'Operation failed') }}</h3>
      <pre>{{ error }}</pre>
    </div>
    <div v-if="output" aria-live="polite">
      <h3>{{ $tu('调用结果', 'Call result') }}</h3>
      <pre>{{ output }}</pre>
    </div>
  </el-drawer>
</template>

<style scoped lang="scss">
pre,
code,
.module-path {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre {
  padding: 12px;
  background: var(--el-fill-color-light);
}
.error-output {
  color: var(--el-color-danger);
}
</style>
