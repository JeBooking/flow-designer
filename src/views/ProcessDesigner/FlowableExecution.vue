<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import { is } from 'bpmn-js/lib/util/ModelUtil'
import type { ModdleElement } from 'bpmn-js/lib/model/Types'
import type { ModelElement } from '@/views/ProcessDesigner/CodeGeneration/generate'
import type { PythonParameter } from '@/types/pythonProject'
import { listPythonProjects } from '@/services/pythonProjects'
import { flowableRequest } from '@/services/flowable'
import { createArchive } from '@/views/ProcessDesigner/CodeGeneration/archive'
import { diagnosticExamples } from '@/views/ProcessDesigner/examples/catalog'
import type { DiagnosisReviewState } from '@/types/diagnosis'
import ReferenceFile from '@/views/ProcessDesigner/Panel/Investigation/ReferenceFile.vue'

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
const currentProcessId = ref('')
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
  currentProcessId.value = processes[0]?.id || ''
  const bindings = new Map<string, { module: string; factory: string; functions: Set<string> }>()
  const visit = (scope: ModelElement) => {
    for (const element of (scope.get('flowElements') as ModelElement[] | undefined) || []) {
      const module = String(element.get('flowable:pythonModule') || '')
      const factory = String(element.get('flowable:pythonFactory') || '')
      const name = String(element.get('flowable:pythonFunction') || '')
      if (module && name) {
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
  if (loadedExample.value && selectedScenario.value) values.set('scenario', selectedScenario.value)
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
const runId = ref('')
const history = ref('')
const charts = ref<string[]>([])
const finished = ref(false)
const visitedNodes = ref<string[]>([])
const review = ref<DiagnosisReviewState>({ pending: false })
const reviewTarget = ref('')
const reviewReason = ref('')
const reviewVariables = ref('{}')
const reviewNext = ref('')
const decisionPending = computed(() => review.value.mode === 'decision')
const successPending = computed(() => review.value.mode === 'success')
const executionVariables = ref<Record<string, unknown>>({})
const pythonFailures = ref<Array<{ id: string; exceptionMessage?: string; traceback?: string }>>([])
const failures = computed(() => {
  const value = executionVariables.value.diagnosticFailures
  return Array.isArray(value) ? value : []
})
const reviewInstructions = computed(() =>
  [
    { label: translateUi('详细内容', 'Details'), value: review.value.instructions?.detailText },
    {
      label: translateUi('查看什么数据', 'Data to inspect'),
      value: review.value.instructions?.observation,
    },
    {
      label: translateUi('如何获取数据', 'How to acquire data'),
      value: review.value.instructions?.acquisition,
    },
    {
      label: translateUi('判断方法', 'Assessment method'),
      value: review.value.instructions?.assessment,
    },
    {
      label: translateUi('结论内容', 'Conclusion'),
      value: review.value.instructions?.conclusionText,
    },
    { label: translateUi('动作内容', 'Action'), value: review.value.instructions?.actionText },
  ].filter((item) => item.value),
)
const currentDiagramId = 'current-diagram'
const selectedExampleId = ref(currentDiagramId)
const selectedExample = computed(() =>
  diagnosticExamples.find((item) => item.id === selectedExampleId.value),
)
const loadedExampleId = ref('')
const loadedExample = computed(() =>
  diagnosticExamples.find((item) => {
    if (item.id !== loadedExampleId.value) return false
    const document = new DOMParser().parseFromString(item.xml, 'application/xml')
    return (
      document
        .getElementsByTagNameNS('http://www.omg.org/spec/BPMN/20100524/MODEL', 'process')[0]
        ?.getAttribute('id') === currentProcessId.value
    )
  }),
)
const selectedScenario = ref('')
const onExampleChange = () => {
  if (selectedExampleId.value !== currentDiagramId) return
  // 切回用户画布时不再注入内置示例的场景变量，保留用户填写的启动输入。
  loadedExampleId.value = ''
  selectedScenario.value = ''
}
const applyScenario = (scenario: string) => {
  selectedScenario.value = scenario
}
interface Bundle {
  files: Record<string, string>
  processId: string
}
async function perform(operation: () => Promise<void>) {
  busy.value = true
  errorMessage.value = ''
  try {
    await operation()
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    busy.value = false
  }
}
async function getXml() {
  const { xml } = await props.modeler.saveXML({ format: true })
  if (!xml) throw new Error(translateUi('无法读取流程', 'Unable to read the process'))
  return xml
}
function download(files: Record<string, string>) {
  const url = URL.createObjectURL(createArchive(files))
  const link = document.createElement('a')
  link.href = url
  link.download = 'flowable-diagnostic.zip'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
const loadDemo = () =>
  perform(async () => {
    const example = selectedExample.value
    if (!example) return
    await ElMessageBox.confirm(
      translateUi(
        '载入示例会替换当前画布，请先导出需要保留的流程。',
        'Loading the example replaces the canvas. Export your current diagram first.',
      ),
      translateUi('载入诊断示例', 'Load diagnostic example'),
      { type: 'warning' },
    )
    await props.modeler.importXML(example.xml)
    loadedExampleId.value = example.id
    additionalInputs.value = []
    Object.keys(startupValues).forEach((key) => delete startupValues[key])
    advancedVariables.value = false
    await reloadStartupInputs()
    selectedScenario.value = example.scenarios[0]
    applyScenario(selectedScenario.value)
    const canvas = props.modeler.get<Canvas>('canvas')
    canvas.zoom('fit-viewport')
    const box = canvas.viewbox()
    canvas.viewbox({
      x: box.x - 110,
      y: box.y - 60,
      width: box.width + 220,
      height: box.height + 120,
    })
    runId.value = ''
    pythonFailures.value = []
    executionVariables.value = {}
    finished.value = false
    history.value = ''
    charts.value = []
    visitedNodes.value = []
    review.value = { pending: false }
  })
const exportBundle = () =>
  perform(async () => {
    const bundle = await flowableRequest<Bundle>('compile', { xml: await getXml() })
    download(bundle.files)
  })
const start = () =>
  perform(async () => {
    const variables = startupVariables()
    const result = await flowableRequest<Bundle & { run: { id: string } }>('start', {
      xml: await getXml(),
      variables,
    })
    runId.value = result.run.id
    pythonFailures.value = []
    executionVariables.value = {}
    finished.value = false
    history.value = ''
    charts.value = []
    visitedNodes.value = []
    review.value = { pending: false }
  })
async function loadExecution() {
  const result = await flowableRequest<{
    process: { endTime?: string }
    activities: { data: { activityType: string; activityId: string; activityName?: string }[] }
    variables: { data: { variable?: { name?: string; value?: unknown } }[] }
    review: DiagnosisReviewState
    failures?: Array<{ id: string; exceptionMessage?: string; traceback?: string }>
  }>(`history/${encodeURIComponent(runId.value)}`)
  history.value = JSON.stringify(result, null, 2)
  pythonFailures.value = result.failures || []
  finished.value = Boolean(result.process.endTime)
  executionVariables.value = Object.fromEntries(
    result.variables.data.flatMap(({ variable }) =>
      variable?.name ? [[variable.name, variable.value]] : [],
    ),
  )
  const previousTaskId = review.value.taskId
  review.value = result.review
  if (previousTaskId !== result.review.taskId) {
    reviewTarget.value = ''
    reviewReason.value = ''
    reviewVariables.value = '{}'
    reviewNext.value = result.review.options?.length === 1 ? result.review.options[0].id : ''
  }
  visitedNodes.value = result.activities.data
    .filter((item) =>
      ['serviceTask', 'externalWorkerServiceTask', 'userTask', 'endEvent'].includes(
        item.activityType,
      ),
    )
    .map((item) => item.activityName || item.activityId)
  charts.value = result.variables.data.flatMap((item) => {
    const value = item.variable?.value
    const svg =
      value && typeof value === 'object' && 'chartSvg' in value ? value.chartSvg : undefined
    return typeof svg === 'string'
      ? [`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`]
      : []
  })
}
const refresh = () => perform(loadExecution)
const submitReview = (action: 'recheck' | 'confirm', successAction?: 'continue' | 'finish') =>
  perform(async () => {
    if (successAction) reviewNext.value = successAction
    if (
      action === 'confirm' &&
      (decisionPending.value || successPending.value) &&
      review.value.options?.length &&
      !reviewNext.value
    ) {
      throw new Error(translateUi('请选择下一步', 'Select the next step'))
    }
    if (action === 'recheck' && (!reviewTarget.value || !reviewReason.value.trim())) {
      throw new Error(
        translateUi('请选择回退节点并填写原因', 'Select a recheck node and provide a reason'),
      )
    }
    const variables: unknown = action === 'recheck' ? JSON.parse(reviewVariables.value) : {}
    if (!variables || typeof variables !== 'object' || Array.isArray(variables)) {
      throw new Error(translateUi('变量必须是 JSON 对象', 'Variables must be a JSON object'))
    }
    await ElMessageBox.confirm(
      action === 'recheck'
        ? translateUi(
            '将重新执行选中节点及后续逻辑，可能再次执行机台动作。原记录保留，但不会撤销已经执行的动作。',
            'The selected node and downstream logic will run again, including possible machine actions. Previous records are retained; completed actions are not undone.',
          )
        : successPending.value
          ? reviewNext.value === 'continue'
            ? translateUi(
                '继续执行暂停的其余排查思路。',
                'Resume the remaining investigation paths.',
              )
            : translateUi(
                '结束本轮排查，保留当前结果和执行记录。',
                'Finish this investigation and retain its results and history.',
              )
          : decisionPending.value
            ? translateUi(
                '确认当前选择并继续执行后续节点。',
                'Confirm this choice and continue to the next node.',
              )
            : translateUi(
                '确认上升后本轮流程结束。',
                'Confirming escalation ends this process instance.',
              ),
      action === 'recheck'
        ? translateUi('回退重查', 'Recheck an earlier node')
        : successPending.value
          ? translateUi('问题已解决', 'Problem solved')
          : decisionPending.value
            ? translateUi('确认并继续', 'Confirm and continue')
            : translateUi('确认上升', 'Confirm escalation'),
      { type: 'warning' },
    )
    await flowableRequest(`review/${encodeURIComponent(runId.value)}`, {
      action,
      taskId: review.value.taskId,
      targetNodeId: reviewTarget.value,
      reason: reviewReason.value,
      variables,
      next: reviewNext.value,
    })
    // 回退后旧页面中的结果不能再作为当前判断依据；历史快照仍保存在执行详情中。
    history.value = ''
    charts.value = []
    visitedNodes.value = []
    review.value = { pending: false }
    finished.value = false
    await loadExecution()
    ElMessage.success(
      translateUi('操作已完成，执行状态已更新', 'Action completed; execution status updated'),
    )
  })
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
    :title="$tu('Flowable 执行', 'Flowable execution')"
    size="min(620px, 100vw)"
  >
    <el-form label-position="top">
      <el-form-item :label="$tu('诊断示例', 'Diagnostic example')">
        <el-select v-model="selectedExampleId" style="width: 100%" @change="onExampleChange">
          <el-option
            :value="currentDiagramId"
            :label="$tu('当前绘制的流程图', 'Current diagram')"
          />
          <el-option
            v-for="example in diagnosticExamples"
            :key="example.id"
            :value="example.id"
            :label="$tu(example.title, example.titleEn)"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <p v-if="selectedExample">
      {{ $tu(selectedExample.description, selectedExample.descriptionEn) }}
    </p>
    <p v-else>
      {{
        $tu(
          '使用当前画布上的节点、连线和函数配置，无需载入示例。执行时读取画布的最新内容。',
          'Use the nodes, connections and function bindings on the current canvas. No example needs to be loaded; execution reads the latest diagram.',
        )
      }}
    </p>
    <el-space wrap>
      <el-button v-if="selectedExample" :disabled="busy" @click="loadDemo">{{
        $tu('载入诊断示例', 'Load diagnostic example')
      }}</el-button>
      <el-button :disabled="busy" @click="exportBundle">{{
        $tu('导出执行包', 'Export execution bundle')
      }}</el-button>
    </el-space>
    <p>
      {{
        $tu(
          '先导出执行包，将 bindings.json 交给 Python 客户端；再启动流程。详见 backend/FLOWABLE.zh-CN.md。',
          'Export the bundle and give bindings.json to the Python worker, then start the process. See backend/FLOWABLE.md.',
        )
      }}
    </p>
    <el-button :disabled="busy" :loading="inputsLoading" @click="reloadStartupInputs">{{
      $tu('重新读取启动输入', 'Reload startup inputs')
    }}</el-button>
    <p v-if="discoveryNotice" role="status">{{ discoveryNotice }}</p>
    <el-form v-if="!advancedVariables" label-position="top" :disabled="busy || inputsLoading">
      <el-form-item v-if="loadedExample" :label="$tu('示例场景', 'Example scenario')">
        <el-select v-model="selectedScenario" @change="applyScenario" style="width: 100%">
          <el-option
            v-for="scenario in loadedExample.scenarios"
            :key="scenario"
            :label="scenario"
            :value="scenario"
          />
        </el-select>
      </el-form-item>
      <p>
        {{
          $tu(
            '此处仅列出会话类或工厂的初始化参数。节点方法的输入可能来自上游结果，额外启动数据可按名称添加。数字、布尔值、null、数组和对象自动识别，其他输入作为文本；空字符串请填双引号。',
            'Only session class or factory initialization parameters are listed here. Method inputs may come from upstream results; add any extra startup data by name. Numbers, booleans, null, arrays and objects are parsed automatically; other input is text. Enter double quotes for an empty string.',
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
    <el-button type="primary" :disabled="inputsLoading" :loading="busy" @click="start">{{
      $tu('部署并启动', 'Deploy and start')
    }}</el-button>
    <el-alert v-if="errorMessage" type="error" :title="errorMessage" :closable="false" show-icon />
    <template v-if="runId">
      <p>{{ $tu('流程实例', 'Process instance') }}: {{ runId }}</p>
      <el-button :disabled="busy" @click="refresh">{{
        $tu('刷新执行结果', 'Refresh execution results')
      }}</el-button>
      <p v-if="history">
        {{
          review.pending
            ? successPending
              ? $tu(
                  '问题已解决，其余思路已暂停，可选择继续排查',
                  'Problem solved; remaining paths are paused. You may continue investigating.',
                )
              : decisionPending
                ? $tu('等待人工判断／确认', 'Awaiting human decision / confirmation')
                : $tu('已到达上升，等待人工复核', 'Escalation reached; awaiting review')
            : finished
              ? $tu('流程已结束', 'Process completed')
              : $tu('正在执行或等待外部任务', 'Running or waiting for an external worker')
        }}
      </p>
      <el-card v-if="review.pending" shadow="never">
        <template #header>{{ $tu('诊断复核', 'Diagnostic review') }}</template>
        <p>{{ review.name }} ({{ review.nodeId }})</p>
        <el-space v-if="successPending" wrap>
          <el-button type="primary" :disabled="busy" @click="submitReview('confirm', 'finish')">
            {{ $tu('结束排查', 'Finish investigation') }}
          </el-button>
          <el-button :disabled="busy" @click="submitReview('confirm', 'continue')">
            {{ $tu('继续排查其余思路', 'Continue remaining paths') }}
          </el-button>
        </el-space>
        <details v-if="review.evidence != null">
          <summary>{{ $tu('查看判断依据数据', 'View decision evidence') }}</summary>
          <pre class="execution-results">{{ JSON.stringify(review.evidence, null, 2) }}</pre>
        </details>
        <img
          v-for="(chart, index) in charts"
          :key="chart"
          :src="chart"
          :alt="
            $tu('Python 生成的诊断图表', 'Diagnostic chart generated by Python') + ` ${index + 1}`
          "
          style="width: 100%; height: auto"
        />
        <template v-for="instruction in reviewInstructions" :key="instruction.label">
          <p>
            <strong>{{ instruction.label }}</strong>
          </p>
          <p class="execution-results">{{ instruction.value }}</p>
        </template>
        <ReferenceFile
          v-if="review.instructions?.referenceImage"
          :value="review.instructions.referenceImage"
          :name="review.instructions.referenceImageName"
          readonly
        />
        <el-form v-if="decisionPending" label-position="top">
          <el-form-item v-if="review.options?.length" :label="$tu('下一步', 'Next step')">
            <el-select v-model="reviewNext" style="width: 100%">
              <el-option
                v-for="option in review.options"
                :key="option.id"
                :value="option.id"
                :label="`${option.name} (${option.id})`"
              />
            </el-select>
          </el-form-item>
          <el-button type="primary" :disabled="busy" @click="submitReview('confirm')">{{
            $tu('确认并继续', 'Confirm and continue')
          }}</el-button>
        </el-form>
        <template v-if="!successPending">
          <el-divider />
          <p v-if="!review.candidates?.length">
            {{
              $tu('尚无此前已执行的节点可供回退。', 'No earlier executed nodes are available yet.')
            }}
          </p>
          <el-form label-position="top">
            <el-form-item
              :label="$tu('回退到此前已执行的节点', 'Return to an earlier executed node')"
            >
              <el-select v-model="reviewTarget" style="width: 100%">
                <el-option
                  v-for="candidate in review.candidates || []"
                  :key="candidate.id"
                  :value="candidate.id"
                  :label="`${candidate.name} (${candidate.id})`"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="$tu('回退原因', 'Recheck reason')">
              <el-input v-model="reviewReason" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item
              :label="$tu('复查输入变量（可选）', 'Updated input variables (optional)')"
            >
              <el-input v-model="reviewVariables" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
          <p>
            {{
              $tu(
                '回退将重新采集和判断，并清理需重算的结果；旧路径与结果保留在复核记录中。',
                'Rechecking reruns acquisition and diagnosis and clears results that must be recomputed. Previous paths and results remain in review history.',
              )
            }}
          </p>
          <el-space wrap>
            <el-button
              :disabled="busy || !review.candidates?.length"
              @click="submitReview('recheck')"
              >{{ $tu('回退重查', 'Recheck') }}</el-button
            >
            <el-button v-if="!decisionPending" :disabled="busy" @click="submitReview('confirm')">{{
              $tu('确认上升并结束', 'Confirm escalation and finish')
            }}</el-button>
          </el-space>
        </template>
      </el-card>
      <p v-if="visitedNodes.length">
        {{ $tu('已执行节点', 'Executed nodes') }}: {{ visitedNodes.join(' → ') }}
      </p>
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
        <pre class="execution-results">{{ JSON.stringify(failures, null, 2) }}</pre>
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
      <template v-if="!review.pending"
        ><img
          v-for="(chart, index) in charts"
          :key="chart"
          :src="chart"
          :alt="
            $tu('Python 生成的诊断图表', 'Diagnostic chart generated by Python') + ` ${index + 1}`
          "
          style="width: 100%; height: auto"
      /></template>
      <details v-if="history">
        <summary>{{ $tu('执行详情', 'Execution details') }}</summary>
        <pre class="execution-results">{{ history }}</pre>
      </details>
    </template>
  </el-drawer>
</template>

<style scoped>
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
