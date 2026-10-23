<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import { flowableRequest } from '@/services/flowable'
import { createArchive } from '@/views/ProcessDesigner/CodeGeneration/archive'
import { diagnosticExamples } from '@/views/ProcessDesigner/examples/catalog'

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
  })
const refresh = () =>
  perform(async () => {
    const result = await flowableRequest<{
      process: { endTime?: string }
      activities: { data: { activityType: string; activityId: string; activityName?: string }[] }
      variables: { data: { variable?: { value?: { chartSvg?: string } } }[] }
    }>(`history/${encodeURIComponent(runId.value)}`)
    history.value = JSON.stringify(result, null, 2)
    finished.value = Boolean(result.process.endTime)
    visitedNodes.value = result.activities.data
      .filter((item) =>
        ['serviceTask', 'externalWorkerServiceTask', 'endEvent'].includes(item.activityType),
      )
      .map((item) => item.activityName || item.activityId)
    charts.value = result.variables.data.flatMap((item) => {
      const svg = item.variable?.value?.chartSvg
      return typeof svg === 'string'
        ? [`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`]
        : []
    })
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
          finished
            ? $tu('流程已结束', 'Process completed')
            : $tu('正在执行或等待外部任务', 'Running or waiting for an external worker')
        }}
      </p>
      <p v-if="visitedNodes.length">
        {{ $tu('已执行节点', 'Executed nodes') }}: {{ visitedNodes.join(' → ') }}
      </p>
      <img
        v-for="(chart, index) in charts"
        :key="chart"
        :src="chart"
        :alt="$tu('Python 生成的温度图', 'Temperature chart generated by Python') + ` ${index + 1}`"
        style="width: 100%; height: auto"
      />
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
