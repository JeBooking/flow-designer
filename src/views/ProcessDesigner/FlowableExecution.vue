<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import { flowableRequest } from '@/services/flowable'
import { createArchive } from '@/views/ProcessDesigner/CodeGeneration/archive'
import { diagnosticExamples } from '@/views/ProcessDesigner/examples/catalog'
import type { DiagnosisReviewState } from '@/types/diagnosis'

const props = defineProps<{ modeler: BpmnModeler }>()
const visible = ref(false)
const busy = ref(false)
const errorMessage = ref('')
const variablesText = ref('{"scenario": "recover"}')
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
const selectedExampleId = ref(diagnosticExamples[0].id)
const selectedExample = computed(
  () =>
    diagnosticExamples.find((item) => item.id === selectedExampleId.value) || diagnosticExamples[0],
)
const loadedExampleId = ref('')
const loadedExample = computed(() =>
  diagnosticExamples.find((item) => item.id === loadedExampleId.value),
)
const selectedScenario = ref('')
const applyScenario = (scenario: string) => {
  variablesText.value = JSON.stringify({ scenario }, null, 2)
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
    await ElMessageBox.confirm(
      translateUi(
        '载入示例会替换当前画布，请先导出需要保留的流程。',
        'Loading the example replaces the canvas. Export your current diagram first.',
      ),
      translateUi('载入诊断示例', 'Load diagnostic example'),
      { type: 'warning' },
    )
    await props.modeler.importXML(selectedExample.value.xml)
    loadedExampleId.value = selectedExample.value.id
    selectedScenario.value = selectedExample.value.scenarios[0]
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
    const variables: unknown = JSON.parse(variablesText.value)
    if (!variables || typeof variables !== 'object' || Array.isArray(variables)) {
      throw new Error(translateUi('变量必须是 JSON 对象', 'Variables must be a JSON object'))
    }
    const result = await flowableRequest<Bundle & { run: { id: string } }>('start', {
      xml: await getXml(),
      variables,
    })
    runId.value = result.run.id
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
  }>(`history/${encodeURIComponent(runId.value)}`)
  history.value = JSON.stringify(result, null, 2)
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
        <el-select v-model="selectedExampleId" style="width: 100%">
          <el-option
            v-for="example in diagnosticExamples"
            :key="example.id"
            :value="example.id"
            :label="$tu(example.title, example.titleEn)"
          />
        </el-select>
      </el-form-item>
    </el-form>
    <p>{{ $tu(selectedExample.description, selectedExample.descriptionEn) }}</p>
    <el-space wrap>
      <el-button :disabled="busy" @click="loadDemo">{{
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
    <el-form label-position="top">
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
      <el-form-item :label="$tu('初始流程变量', 'Initial process variables')">
        <el-input v-model="variablesText" type="textarea" :rows="4" />
      </el-form-item>
    </el-form>
    <el-button type="primary" :loading="busy" @click="start">{{
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
        <img
          v-if="review.instructions?.referenceImage"
          :src="review.instructions.referenceImage"
          :alt="$tu('诊断参考图', 'Diagnostic reference image')"
          style="max-width: 100%"
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
</style>
