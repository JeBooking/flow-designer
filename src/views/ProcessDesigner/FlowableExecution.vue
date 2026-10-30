<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import type { ModelElement } from '@/views/ProcessDesigner/CodeGeneration/generate'
import type { PythonParameter } from '@/types/pythonProject'
import type { DiagnosticFailure } from '@/types/flowableExecution'
import { listPythonProjects } from '@/services/pythonProjects'
import { flowableRequest } from '@/services/flowable'
import { useExecution } from '@/views/ProcessDesigner/Execution/useExecution'
import ExecutionProgress from '@/views/ProcessDesigner/Execution/ExecutionProgress.vue'
import ExecutionReviewTask from '@/views/ProcessDesigner/Execution/ExecutionReviewTask.vue'
import ExecutionTaskWindows from '@/views/ProcessDesigner/Execution/ExecutionTaskWindows.vue'
import ExecutionNodeHistory from '@/views/ProcessDesigner/Execution/ExecutionNodeHistory.vue'
import ExecutionCanvasOverlays from '@/views/ProcessDesigner/Execution/ExecutionCanvasOverlays.vue'

const props = defineProps<{ modeler: BpmnModeler }>()
const visible = ref(false)
const busy = ref(false)
const errorMessage = ref('')
const variablesText = ref('{}')
const advancedVariables = ref(false)
interface StartupParameter extends PythonParameter {
  sources: string[]
}
interface StartupInput {
  id: number
  name: string
  value: string
}
const startupParameters = ref<StartupParameter[]>([])
const startupValues = reactive<Record<string, string>>({})
const additionalInputs = ref<StartupInput[]>([])
let nextInputId = 0
const inputsLoading = ref(false)
const discoveryNotice = ref('')
const addStartupInput = () => {
  additionalInputs.value = [...additionalInputs.value, { id: ++nextInputId, name: '', value: '' }]
}
const parseInput = (value: string): unknown => {
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}
async function reloadStartupInputs() {
  inputsLoading.value = true
  discoveryNotice.value = ''
  startupParameters.value = []
  const definitions = props.modeler.getDefinitions() as ModelElement | undefined
  const roots = (definitions?.get('rootElements') as ModelElement[] | undefined) || []
  const processes = roots.filter((element) => is(element as ModdleElement, 'bpmn:Process'))
  const bindings = new Map<string, { module: string; factory: string; functions: Set<string> }>()
  const visit = (scope: ModelElement) => {
    for (const element of (scope.get('flowElements') as ModelElement[] | undefined) || []) {
      const module = String(element.get('flowable:pythonModule') || '')
      const factory = String(element.get('flowable:pythonFactory') || '')
      const name = String(element.get('flowable:pythonFunction') || '')
      const kind = element.get('flowable:diagnosisKind')
      const manualAction =
        (kind === 'remediation' || kind === 'investigationAction') &&
        element.get('flowable:actionMode') === 'manual'
      // 人工执行保留旧接口供切回使用，但它不参与本次运行的参数发现。
      if (!manualAction && module && name) {
        const key = JSON.stringify([module, factory])
        const binding = bindings.get(key) || { module, factory, functions: new Set<string>() }
        binding.functions.add(name)
        bindings.set(key, binding)
      }
      if (is(element as ModdleElement, 'bpmn:SubProcess')) visit(element)
    }
  }
  processes.forEach(visit)
  try {
    if (!bindings.size) return
    const { projects } = await listPythonProjects()
    const parameters = new Map<string, StartupParameter>()
    let unknown = false
    for (const binding of bindings.values()) {
      const project = projects.find(
        (entry) => entry.module === binding.module && (entry.factory || '') === binding.factory,
      )
      if (
        !project ||
        [...binding.functions].some(
          (name) => !project.interfaces.some((entry) => entry.name === name),
        )
      )
        unknown = true
      if (!binding.factory) continue
      if (!project?.initParameters) {
        unknown = true
        continue
      }
      for (const parameter of project.initParameters) {
        if (parameter.kind === 'VAR_POSITIONAL' || parameter.kind === 'VAR_KEYWORD') continue
        const existing = parameters.get(parameter.name)
        const source = `${binding.module} · ${binding.factory}`
        parameters.set(parameter.name, {
          ...parameter,
          required: parameter.required || Boolean(existing?.required),
          sources: [...(existing?.sources || []), source],
        })
      }
    }
    startupParameters.value = [...parameters.values()]
    if (unknown)
      discoveryNotice.value = translateUi(
        '部分接口签名尚未登记。可添加启动输入；也可在 Python 项目接入中登记后重新读取。',
        'Some signatures are not registered. Add startup inputs, or register the Python project and reload inputs.',
      )
  } catch (failure) {
    discoveryNotice.value =
      translateUi(
        '无法读取已登记签名，可手动添加启动输入：',
        'Unable to read registered signatures. You can add startup inputs manually: ',
      ) + (failure instanceof Error ? failure.message : String(failure))
  } finally {
    inputsLoading.value = false
  }
}
function startupVariables(): Record<string, unknown> {
  if (advancedVariables.value) {
    const value: unknown = JSON.parse(variablesText.value)
    if (!value || typeof value !== 'object' || Array.isArray(value))
      throw new Error(translateUi('变量必须是 JSON 对象', 'Variables must be a JSON object'))
    return value as Record<string, unknown>
  }
  const values = new Map<string, unknown>()
  for (const parameter of startupParameters.value) {
    const raw = startupValues[parameter.name] || ''
    if (!raw.trim()) continue
    values.set(parameter.name, parseInput(raw))
  }
  for (const input of additionalInputs.value) {
    if (!input.name.trim() && !input.value.trim()) continue
    const name = input.name.trim()
    if (!name || values.has(name))
      throw new Error(
        translateUi(
          '启动输入名称不能为空或重复：',
          'Startup input names must be nonempty and unique: ',
        ) + name,
      )
    values.set(name, parseInput(input.value))
  }
  return Object.fromEntries(values)
}
const {
  runId,
  snapshot,
  pendingReviews,
  variables: executionVariables,
  status,
  terminal,
  nodeViews,
  canvasMatches,
  connectionError,
  loading: executionLoading,
  capture,
  begin,
  load: loadExecution,
  reloadAfterReview,
  restore,
  detach,
  recentRunIds,
} = useExecution(props.modeler, visible)
const monitorId = ref('')
const restoreMonitoring = () =>
  perform(async () => {
    await restore(monitorId.value.trim())
    ElMessage.success(translateUi('已恢复实例监控', 'Instance monitoring restored'))
  })
const history = computed(() => (snapshot.value ? JSON.stringify(snapshot.value, null, 2) : ''))
const taskWindows = ref<InstanceType<typeof ExecutionTaskWindows>>()
const selectedNodeId = ref('')
const selectedNode = computed(() =>
  canvasMatches.value && snapshot.value
    ? nodeViews.value.find((node) => node.id === selectedNodeId.value)
    : undefined,
)
const nodeDialogVisible = computed({
  get: () => Boolean(selectedNode.value),
  set: (opened: boolean) => {
    if (!opened) {
      selectedNodeId.value = ''
    }
  },
})
function selectNode(nodeId: string) {
  if (!canvasMatches.value || !snapshot.value) return
  const node = nodeViews.value.find((entry) => entry.id === nodeId)
  if (!node || (node.status !== 'waiting' && node.status !== 'completed')) return
  if (node.status === 'waiting') {
    visible.value = false
    for (const task of pendingReviews.value.filter((entry) => entry.nodeId === nodeId)) {
      if (task.taskId) taskWindows.value?.open(task.taskId)
    }
    return
  }
  visible.value = false
  selectedNodeId.value = nodeId
}
watch(
  [runId, canvasMatches],
  () => {
    selectedNodeId.value = ''
  },
  { flush: 'sync' },
)
watch(
  selectedNode,
  (node) => {
    if (!node) {
      selectedNodeId.value = ''
    }
  },
  { flush: 'sync' },
)
const pythonFailures = computed(() => snapshot.value?.failures || [])
const checkpointStates = computed(() =>
  Object.entries(executionVariables.value).flatMap(([name, value]) => {
    if (
      !name.startsWith('pythonCheckpoint_') ||
      !value ||
      typeof value !== 'object' ||
      !('recoverable' in value)
    )
      return []
    return [
      {
        name,
        recoverable: value.recoverable === true,
        reason: 'reason' in value && typeof value.reason === 'string' ? value.reason : '',
      },
    ]
  }),
)
const previousRunIds = ref<string[]>([])
const canStart = computed(
  () =>
    !pendingReviews.value.length &&
    (!runId.value || terminal.value || pythonFailures.value.length > 0),
)
const restartingFailure = computed(() => Boolean(runId.value) && status.value === 'failed')
const failures = computed(() => {
  const value = executionVariables.value.diagnosticFailures
  return Array.isArray(value)
    ? value.filter((entry): entry is DiagnosticFailure => entry && typeof entry === 'object')
    : []
})
function failureDescription(failure: DiagnosticFailure) {
  if (failure.code === 'route/no-outgoing')
    return translateUi('排查节点没有后续路径', 'Investigation has no outgoing paths')
  if (failure.code === 'route/unmatched-branch')
    return translateUi('判断结果没有匹配出口', 'The decision has no matching outgoing branch')
  return failure.reason || translateUi('历史失败记录', 'Historical failure record')
}

// 只在出现新任务时让出画布，轮询相同任务不打断用户重新打开的执行面板。
watch(
  () =>
    [
      runId.value,
      canvasMatches.value,
      pendingReviews.value.map((task) => task.taskId).join('\n'),
    ] as const,
  ([id, matches, tasks], previous) => {
    if (!matches || !tasks) return
    const earlier =
      previous?.[0] === id && previous[1] ? new Set(previous[2].split('\n')) : new Set<string>()
    if (tasks.split('\n').some((task) => !earlier.has(task))) visible.value = false
  },
  { flush: 'sync' },
)
function openTask(taskId?: string) {
  if (!taskId) return
  visible.value = false
  taskWindows.value?.open(taskId)
}
async function perform(operation: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  errorMessage.value = ''
  try {
    await operation()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    errorMessage.value = error instanceof Error ? error.message : String(error)
    ElMessage.error(errorMessage.value)
  } finally {
    busy.value = false
  }
}
async function getXml() {
  const { xml } = await props.modeler.saveXML({ format: true })
  if (!xml) throw new Error(translateUi('无法读取流程', 'Unable to read the process'))
  return xml
}
const start = () => {
  if (!canStart.value) return
  return perform(async () => {
    if (restartingFailure.value) {
      await ElMessageBox.confirm(
        translateUi(
          '重新执行不会取消旧实例，也不会撤销已经完成的机台动作；同一动作可能再次执行。请记录旧实例 ID：',
          'Restarting does not cancel the previous instance or undo completed machine actions. The same actions may run again. Keep the previous instance ID: ',
        ) + runId.value,
        translateUi('重新执行当前流程', 'Run the current diagram again'),
        { type: 'warning' },
      )
    }
    const variables = startupVariables()
    const captured = capture()
    const xml = await getXml()
    const result = await flowableRequest<{ run: { id: string } }>('start', { xml, variables })
    if (runId.value) previousRunIds.value = [...new Set([...previousRunIds.value, runId.value])]
    begin(result.run.id, captured)
    await loadExecution()
  })
}
const refresh = () => void loadExecution()
defineExpose({
  open: () => {
    visible.value = true
    void reloadStartupInputs()
  },
})
</script>

<template>
  <el-drawer
    v-model="visible"
    :title="$tu('诊断执行', 'Diagnostic execution')"
    :modal="false"
    :modal-penetrable="true"
    :lock-scroll="false"
    :close-on-click-modal="false"
    size="min(620px, 100vw)"
  >
    <el-form label-position="top" @submit.prevent="restoreMonitoring">
      <el-form-item :label="$tu('恢复已有实例监控', 'Resume monitoring an existing instance')">
        <el-select
          v-model="monitorId"
          filterable
          allow-create
          default-first-option
          :disabled="busy"
          :placeholder="$tu('输入或选择流程实例 ID', 'Enter or select a process instance ID')"
        >
          <el-option v-for="id in recentRunIds" :key="id" :label="id" :value="id" />
        </el-select>
      </el-form-item>
      <el-button native-type="submit" :loading="busy" :disabled="!monitorId.trim() || busy">
        {{ $tu('恢复监控', 'Resume monitoring') }}
      </el-button>
      <el-button v-if="runId" :disabled="busy" @click="detach">{{
        $tu('停止监控', 'Stop monitoring')
      }}</el-button>
      <p>
        {{
          $tu(
            '查看已有实例并继续其待办，不会新建执行。',
            'View an existing instance and continue its pending tasks without starting a new run.',
          )
        }}
      </p>
      <p v-if="runId">
        {{
          $tu(
            '停止监控不会取消流程实例。',
            'Stopping monitoring does not cancel the process instance.',
          )
        }}
      </p>
    </el-form>
    <p>
      {{
        $tu(
          '使用当前画布的最新节点、连线和函数配置开始执行。',
          'Execute the latest nodes, connections and function bindings on the current canvas.',
        )
      }}
    </p>
    <el-button :disabled="busy" :loading="inputsLoading" @click="reloadStartupInputs">{{
      $tu('重新读取启动输入', 'Reload startup inputs')
    }}</el-button>
    <p v-if="discoveryNotice" role="status">{{ discoveryNotice }}</p>
    <p
      v-if="
        !inputsLoading &&
        !discoveryNotice &&
        !startupParameters.some((parameter) => parameter.required)
      "
      role="status"
    >
      {{
        $tu(
          '未发现必填启动输入，可直接开始执行；可选输入留空会保留 Python 默认值。',
          'No required startup inputs were found. You can start directly; blank optional inputs preserve Python defaults.',
        )
      }}
    </p>
    <el-form v-if="!advancedVariables" label-position="top" :disabled="busy || inputsLoading">
      <p>
        {{
          $tu(
            '此处列出工程业务对象的初始化参数。节点方法的输入可能来自上游结果，额外启动数据可按名称添加。数字、布尔值、null、数组和对象自动识别，其他输入作为文本；空字符串请填双引号。',
            'Initialization parameters for the project business object are listed here. Method inputs may come from upstream results; add any extra startup data by name. Numbers, booleans, null, arrays and objects are parsed automatically; other input is text. Enter double quotes for an empty string.',
          )
        }}
      </p>
      <p v-if="startupParameters.length">
        {{
          $tu(
            '启动变量按名称全局共享。多个工程或工厂的同名初始化参数使用同一输入值；可选参数留空时，各自保留 Python 默认值。',
            'Startup variables are shared globally by name. Initialization parameters with the same name across projects or factories share one value. Blank optional fields preserve each Python default.',
          )
        }}
      </p>
      <el-form-item
        v-for="parameter in startupParameters"
        :key="parameter.name"
        :label="parameter.name + (parameter.annotation ? ' · ' + parameter.annotation : '')"
      >
        <el-input
          v-model="startupValues[parameter.name]"
          :placeholder="
            parameter.default !== undefined
              ? $tu('默认：', 'Default: ') + parameter.default
              : $tu('输入值', 'Enter a value')
          "
        />
        <el-text size="small" type="info">{{ parameter.sources.join(' / ') }}</el-text>
        <el-text v-if="parameter.required" size="small" type="info">
          {{
            $tu(
              'Python 无默认值：请提供启动值，或确保初始化前由上游提供。',
              'No Python default: provide a startup value or supply it upstream before initialization.',
            )
          }}
        </el-text>
      </el-form-item>
      <div v-for="input in additionalInputs" :key="input.id" class="startup-input">
        <el-form-item :label="$tu('输入名称', 'Input name')"
          ><el-input v-model="input.name"
        /></el-form-item>
        <el-form-item :label="$tu('输入值', 'Input value')"
          ><el-input v-model="input.value"
        /></el-form-item>
        <el-button
          @click="additionalInputs = additionalInputs.filter((item) => item.id !== input.id)"
          >{{ $tu('移除', 'Remove') }}</el-button
        >
      </div>
      <el-button @click="addStartupInput">{{ $tu('添加启动输入', 'Add startup input') }}</el-button>
    </el-form>
    <details class="advanced-inputs">
      <summary>{{ $tu('高级：初始变量 JSON', 'Advanced: initial variables JSON') }}</summary>
      <el-switch
        v-model="advancedVariables"
        :disabled="busy"
        :active-text="$tu('使用 JSON 代替表单', 'Use JSON instead of the form')"
      />
      <el-input
        v-if="advancedVariables"
        v-model="variablesText"
        type="textarea"
        :rows="4"
        :disabled="busy"
        :aria-label="$tu('初始流程变量 JSON', 'Initial process variables JSON')"
      />
    </details>
    <el-button
      type="primary"
      :disabled="inputsLoading || !canStart"
      :loading="busy"
      @click="start"
      >{{
        restartingFailure
          ? $tu('重新执行当前流程', 'Run the current diagram again')
          : $tu('开始执行', 'Start execution')
      }}</el-button
    >
    <el-alert v-if="errorMessage" type="error" :title="errorMessage" :closable="false" show-icon />
    <template v-if="runId">
      <p>{{ $tu('流程实例', 'Process instance') }}: {{ runId }}</p>
      <el-alert
        v-for="state in checkpointStates"
        :key="state.name"
        :closable="false"
        :type="state.recoverable ? 'success' : 'warning'"
        :title="
          state.recoverable
            ? $tu('最近一次业务检查点已保存', 'Latest business checkpoint saved')
            : $tu(
                '此工程暂不可从检查点恢复，等待期间会保留会话',
                'This project cannot restore a checkpoint yet; its session stays available while waiting',
              )
        "
      >
        <details v-if="state.reason">
          <summary>{{ $tu('检查点说明', 'Checkpoint details') }}</summary>
          {{ state.reason }}
        </details>
      </el-alert>
      <details v-if="previousRunIds.length">
        <summary>{{ $tu('此前的执行实例 ID', 'Previous execution instance IDs') }}</summary>
        <p>
          {{
            $tu(
              '新执行不会取消此前实例，也不会撤销已完成的动作。',
              'New executions do not cancel previous instances or undo completed actions.',
            )
          }}
        </p>
        <ul>
          <li v-for="id in previousRunIds" :key="id">
            <code>{{ id }}</code>
          </li>
        </ul>
      </details>
      <el-button :disabled="busy || executionLoading" @click="refresh">{{
        $tu('刷新执行结果', 'Refresh execution results')
      }}</el-button>
      <ExecutionProgress
        :status="status"
        :nodes="nodeViews"
        :connection-error="connectionError"
        :canvas-matches="canvasMatches"
        :loading="executionLoading"
      />
      <section v-if="pendingReviews.length" class="pending-reviews">
        <h3>{{ $tu('待处理任务', 'Pending tasks') }} ({{ pendingReviews.length }})</h3>
        <el-button v-if="canvasMatches" @click="taskWindows?.arrange()">{{
          $tu('自动排布浮窗', 'Arrange task windows')
        }}</el-button>
        <template v-for="task in pendingReviews" :key="task.taskId">
          <el-button v-if="canvasMatches" @click="openTask(task.taskId)"
            >{{ task.name || task.nodeId }} · {{ $tu('打开任务', 'Open task') }}</el-button
          >
          <el-card v-else shadow="never">
            <ExecutionReviewTask
              :run-id="runId"
              :review="task"
              :connected="!connectionError"
              @submitted="reloadAfterReview"
              @refresh="loadExecution"
            />
          </el-card>
        </template>
      </section>
      <el-alert
        v-if="executionVariables.diagnosticStatus === 'failed'"
        type="error"
        :closable="false"
        :title="$tu('所有排查思路均已失败', 'All investigation paths failed')"
      />
      <details v-if="failures.length">
        <summary>
          {{ $tu('排查思路失败记录', 'Failed investigation paths') }} ({{ failures.length }})
        </summary>
        <ol>
          <li v-for="(failure, index) in failures" :key="failure.id || index">
            <strong
              >{{ failure.nodeId || failure.node }} · {{ failureDescription(failure) }}</strong
            >
            <p v-if="failure.branch">{{ $tu('判断结果', 'Decision') }}: {{ failure.branch }}</p>
            <p v-if="failure.path?.length">
              {{ $tu('排查路径', 'Investigation path') }}: {{ failure.path.join(' → ') }}
            </p>
            <details>
              <summary>{{ $tu('原始记录', 'Raw record') }}</summary>
              <pre class="execution-results">{{ JSON.stringify(failure, null, 2) }}</pre>
            </details>
          </li>
        </ol>
      </details>
      <el-alert
        v-for="failure in pythonFailures"
        :key="failure.id"
        type="error"
        :closable="false"
        :title="failure.exceptionMessage || $tu('Python 调用失败', 'Python call failed')"
      >
        <details v-if="failure.traceback">
          <summary>{{ $tu('原始 Python 异常堆栈', 'Original Python traceback') }}</summary>
          <pre class="execution-results">{{ failure.traceback }}</pre>
        </details>
      </el-alert>
      <details v-if="history">
        <summary>{{ $tu('原始执行详情', 'Raw execution details') }}</summary>
        <pre class="execution-results">{{ history }}</pre>
      </details>
    </template>
  </el-drawer>
  <ExecutionCanvasOverlays
    :modeler="modeler"
    :nodes="nodeViews"
    :run-id="runId"
    :enabled="canvasMatches && !!snapshot"
    @select="selectNode"
  />
  <ExecutionTaskWindows
    ref="taskWindows"
    :modeler="modeler"
    :run-id="runId"
    :reviews="pendingReviews"
    :enabled="canvasMatches && !!snapshot"
  >
    <template #default="{ review: task }">
      <ExecutionReviewTask
        :key="task.taskId"
        :show-heading="false"
        :run-id="runId"
        :review="task"
        :connected="!connectionError"
        @submitted="reloadAfterReview"
        @refresh="loadExecution"
      />
    </template>
  </ExecutionTaskWindows>
  <el-dialog
    v-model="nodeDialogVisible"
    :title="$tu('节点执行记录', 'Node execution history')"
    width="min(680px, calc(100vw - 24px))"
    append-to-body
  >
    <template v-if="selectedNode">
      <p>{{ $tu('流程实例', 'Process instance') }}: {{ runId }}</p>
      <p v-if="busy" role="status">{{ $tu('正在处理操作…', 'Processing action…') }}</p>
      <el-alert
        v-if="errorMessage"
        type="error"
        :title="errorMessage"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="connectionError"
        type="error"
        :title="connectionError"
        :closable="false"
        show-icon
      />
      <ExecutionNodeHistory :node="selectedNode" />
    </template>
  </el-dialog>
</template>

<style scoped>
.pending-reviews {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  margin-block: 16px;
}
.pending-reviews :deep(.el-button) {
  margin-left: 0;
}
.execution-results {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.el-alert {
  margin-top: 16px;
  white-space: pre-wrap;
}
.startup-input {
  margin-block: 16px;
  padding: 12px;
  border: 1px solid var(--el-border-color);
}
.advanced-inputs {
  margin-block: 16px;
}
</style>

<style>
/* 标记只覆盖渲染层，避免改变模型配色或进入命令栈；直接子级选择器对应 diagram-js 图形结构。 */
.djs-element.execution-active > .djs-visual > :first-child {
  stroke: var(--el-color-primary) !important;
  stroke-width: 4px !important;
}
.djs-element.execution-waiting > .djs-visual > :first-child {
  stroke: var(--el-color-warning) !important;
  stroke-width: 4px !important;
  stroke-dasharray: 6 3 !important;
}
.djs-element.execution-completed > .djs-visual > :first-child {
  stroke: var(--el-color-success) !important;
  stroke-width: 3px !important;
}
.djs-element.execution-failed > .djs-visual > :first-child {
  stroke: var(--el-color-danger) !important;
  stroke-width: 4px !important;
  stroke-dasharray: 3 3 !important;
}
</style>
