<script setup lang="ts">
import type {
  PythonProject,
  PythonProjectRegistration,
  PythonInterface,
  PythonParameter,
} from '@/types/pythonProject'
import {
  listPythonProjects,
  registerPythonProject,
  refreshPythonProject,
  removePythonProject,
  callPythonInterface,
  closePythonSession,
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
  factory: '',
  python: '',
})
const error = ref('')
const activeFunction = ref<PythonInterface>()
const parameterValues = reactive<Record<string, string>>({})
const initValues = reactive<Record<string, string>>({})
const output = ref('')
const session = ref<{ projectId: string; id: string }>()
const resetSession = async () => {
  const current = session.value
  if (!current) return
  await closePythonSession(current.projectId, current.id)
  session.value = undefined
}
const resetSelection = async () => {
  busy.value = true
  activeFunction.value = undefined
  output.value = ''
  try {
    await resetSession()
    Object.keys(initValues).forEach((key) => delete initValues[key])
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const resetDebugSession = async () => {
  busy.value = true
  error.value = ''
  try {
    await resetSession()
    output.value = ''
  } catch (failure) {
    error.value = describe(failure)
  } finally {
    busy.value = false
  }
}
const parameterGroups = computed(() => [
  {
    title: translateUi('会话初始化参数', 'Session initialization parameters'),
    parameters: session.value
      ? []
      : (selected.value?.initParameters || []).filter(
          (parameter) => parameter.kind !== 'VAR_POSITIONAL' && parameter.kind !== 'VAR_KEYWORD',
        ),
    values: initValues,
  },
  {
    title: translateUi('接口参数', 'Function parameters'),
    parameters: activeFunction.value?.parameters || [],
    values: parameterValues,
  },
])
const isVariadic = (parameter: PythonParameter) =>
  parameter.kind === 'VAR_POSITIONAL' || parameter.kind === 'VAR_KEYWORD'
const parseValue = (value: string): unknown => {
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}
const displayResult = (value: unknown, representation?: 'json' | 'repr') => {
  if (
    value &&
    typeof value === 'object' &&
    'native' in value &&
    value.native === true &&
    'representation' in value &&
    typeof value.representation === 'string'
  )
    return `${value.representation}\n${JSON.stringify(value, null, 2)}`
  return representation === 'repr' && typeof value === 'string'
    ? value
    : JSON.stringify(value, null, 2)
}
const readValues = (parameters: PythonParameter[], values: Record<string, string>) => {
  const supplied: Record<string, unknown> = {}
  for (const parameter of parameters) {
    const raw = values[parameter.name] || ''
    if (!raw.trim()) {
      if (parameter.required)
        throw new Error(
          translateUi('请填写必填参数：', 'Enter the required parameter: ') + parameter.name,
        )
      continue
    }
    supplied[parameter.name] = parseValue(raw)
  }
  return supplied
}
const buildArguments = (parameters: PythonParameter[], values: Record<string, unknown>) => {
  const args: unknown[] = []
  const kwargs: Record<string, unknown> = {}
  const variadic = parameters.find((parameter) => parameter.kind === 'VAR_POSITIONAL')
  const extra = variadic ? values[variadic.name] : undefined
  if (extra !== undefined && !Array.isArray(extra))
    throw new Error(translateUi('*args 须为 JSON 数组', '*args must be a JSON array'))
  const hasExtra = Array.isArray(extra) && extra.length > 0
  let omittedPositional = false
  for (const parameter of parameters) {
    const value = values[parameter.name]
    if (parameter.kind === 'VAR_POSITIONAL') continue
    if (parameter.kind === 'VAR_KEYWORD') {
      if (value !== undefined) {
        if (!value || typeof value !== 'object' || Array.isArray(value))
          throw new Error(translateUi('**kwargs 须为 JSON 对象', '**kwargs must be a JSON object'))
        Object.assign(kwargs, value)
      }
    } else if (
      parameter.kind === 'POSITIONAL_ONLY' ||
      (hasExtra && parameter.kind === 'POSITIONAL_OR_KEYWORD')
    ) {
      if (value === undefined) omittedPositional = true
      else {
        if (omittedPositional)
          throw new Error(
            translateUi(
              '使用后续位置参数前，请填写此前的位置参数默认值',
              'Supply preceding positional defaults before later positional arguments',
            ),
          )
        args.push(value)
      }
    } else if (value !== undefined) kwargs[parameter.name] = value
  }
  if (hasExtra) {
    if (omittedPositional)
      throw new Error(
        translateUi(
          '使用 *args 前，请填写所有位置参数',
          'Supply all positional parameters before *args',
        ),
      )
    args.push(...extra)
  }
  return { args, kwargs }
}
const describe = (failure: unknown) =>
  failure instanceof Error ? failure.message : String(failure)
const load = async () => {
  loading.value = true
  error.value = ''
  try {
    projects.value = (await listPythonProjects()).projects
    if (!projects.value.some((p) => p.id === selectedId.value)) {
      await resetSession()
      activeFunction.value = undefined
      Object.keys(initValues).forEach((key) => delete initValues[key])
      selectedId.value = projects.value[0]?.id || ''
    }
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
onBeforeUnmount(() => {
  void resetSession().catch(() => undefined)
})
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
    await resetSession()
    const { project } = await registerPythonProject({ ...registration })
    Object.keys(initValues).forEach((key) => delete initValues[key])
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
    await resetSession()
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
    await resetSession()
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
  Object.keys(parameterValues).forEach((key) => delete parameterValues[key])
}
const call = async () => {
  if (!selected.value || !activeFunction.value) return
  busy.value = true
  error.value = ''
  output.value = ''
  try {
    if (session.value && session.value.projectId !== selected.value.id) await resetSession()
    const { args, kwargs } = buildArguments(
      activeFunction.value.parameters || [],
      readValues(activeFunction.value.parameters || [], parameterValues),
    )
    const inputs = session.value
      ? undefined
      : readValues(selected.value.initParameters || [], initValues)
    const result = await callPythonInterface(
      selected.value.id,
      activeFunction.value.name,
      args,
      kwargs,
      session.value?.id,
      inputs,
    )
    if (result.sessionId) session.value = { projectId: selected.value.id, id: result.sessionId }
    output.value = [
      displayResult(result.result, result.representation),
      result.stdout,
      result.stderr,
      result.error,
      result.traceback,
    ]
      .filter((value) => value !== undefined && value !== '')
      .join('\n')
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
    factory: '',
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
      <el-form-item :label="$tu('会话类或工厂（可选）', 'Session class or factory (optional)')">
        <el-input v-model="registration.factory" placeholder="Device / create_session" />
      </el-form-item>
      <p>
        {{
          $tu(
            '留空使用模块普通函数。填写类名或工厂路径后，每次排查创建一个实例，同次排查的接口共享其原生对象。无返回类注解的工厂会在接入时临时初始化一次以发现接口。',
            'Leave blank for module functions. A class or factory creates one instance per investigation, sharing native objects between its calls. Factories without a return class annotation are initialized temporarily during registration to discover methods.',
          )
        }}
      </p>
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
            :label="`${project.name} (${project.module}${project.factory ? ' · ' + project.factory : ''})`"
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
      <p>
        {{
          $tu(
            '数字、布尔值、null、数组和对象自动识别，其他输入按文本传递；空字符串请填双引号。可选参数留空使用 Python 默认值。',
            'Numbers, booleans, null, arrays and objects are parsed automatically; other input is text. Enter double quotes for an empty string. Leave optional fields blank to use Python defaults.',
          )
        }}
      </p>
      <template v-for="group in parameterGroups" :key="group.title">
        <template v-if="group.parameters.length">
          <h4>{{ group.title }}</h4>
          <template v-for="parameter in group.parameters" :key="parameter.name">
            <el-form-item
              v-if="!isVariadic(parameter)"
              :label="parameter.name + (parameter.annotation ? ' · ' + parameter.annotation : '')"
              :required="parameter.required"
            >
              <el-input
                v-model="group.values[parameter.name]"
                :placeholder="
                  parameter.default !== undefined
                    ? $tu('默认：', 'Default: ') + parameter.default
                    : $tu('输入值', 'Enter a value')
                "
              />
            </el-form-item>
            <el-collapse v-else>
              <el-collapse-item
                :title="$tu('高级可变参数', 'Advanced variadic arguments') + ' · ' + parameter.name"
              >
                <el-form-item
                  :label="
                    parameter.kind === 'VAR_POSITIONAL'
                      ? $tu('*args（JSON 数组）', '*args (JSON array)')
                      : $tu('**kwargs（JSON 对象）', '**kwargs (JSON object)')
                  "
                >
                  <el-input v-model="group.values[parameter.name]" type="textarea" :rows="2" />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>
          </template>
        </template>
      </template>
      <p>
        {{
          session
            ? $tu(
                '调试会话已建立，后续调用复用当前实例。',
                'Debug session active; subsequent calls reuse this instance.',
              )
            : $tu('首次调用将创建调试会话。', 'The first call creates a debug session.')
        }}
      </p>
      <el-button :disabled="!session" @click="resetDebugSession">{{
        $tu('重置调试会话', 'Reset debug session')
      }}</el-button>
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
