import type { Ref } from 'vue'
import type Modeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import type ElementRegistry from 'diagram-js/lib/core/ElementRegistry'
import type EventBus from 'diagram-js/lib/core/EventBus'
import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import { flowableRequest } from '@/services/flowable'
import type {
  ExecutionHistory,
  ExecutionInstructions,
  ExecutionNode,
  ExecutionNodeStatus,
  ExecutionNodeView,
  ExecutionStatus,
  ExecutionTrace,
  ExecutionReview,
} from '@/types/flowableExecution'

function parseStoredJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return undefined
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function optionalString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function parseInstructions(value: unknown): ExecutionInstructions | undefined {
  if (!isRecord(value)) return undefined
  return {
    observation: optionalString(value.observation),
    acquisition: optionalString(value.acquisition),
    assessment: optionalString(value.assessment),
    referenceImage: optionalString(value.referenceImage),
    referenceImageName: optionalString(value.referenceImageName),
    detailText: optionalString(value.detailText),
    conclusionText: optionalString(value.conclusionText),
    actionText: optionalString(value.actionText),
  }
}

function parseTrace(value: unknown): ExecutionTrace | undefined {
  const entry = parseStoredJson(value)
  if (
    !isRecord(entry) ||
    entry.version !== 1 ||
    typeof entry.id !== 'string' ||
    !entry.id ||
    typeof entry.nodeId !== 'string' ||
    !entry.nodeId ||
    typeof entry.startedAt !== 'string' ||
    typeof entry.endedAt !== 'string' ||
    (entry.status !== 'completed' && entry.status !== 'waiting' && entry.status !== 'failed')
  )
    return undefined
  return {
    version: 1,
    id: entry.id,
    nodeId: entry.nodeId,
    jobId: optionalString(entry.jobId),
    startedAt: entry.startedAt,
    endedAt: entry.endedAt,
    status: entry.status,
    inputs: entry.inputs,
    ...(Object.prototype.hasOwnProperty.call(entry, 'factoryInputs')
      ? { factoryInputs: entry.factoryInputs }
      : {}),
    evidence: entry.evidence,
    result: entry.result,
    route: entry.route,
    instructions: parseInstructions(entry.instructions),
    judgmentInstructions: optionalString(entry.judgmentInstructions),
    error: entry.error,
    traceback: optionalString(entry.traceback),
    call: isRecord(entry.call)
      ? {
          module: optionalString(entry.call.module),
          factory: optionalString(entry.call.factory),
          function: optionalString(entry.call.function),
        }
      : undefined,
  }
}

function parseReviews(value: unknown): ExecutionReview[] {
  const entries = parseStoredJson(value)
  if (!Array.isArray(entries)) return []
  return entries.filter(isRecord).map((entry) => ({
    mode:
      entry.mode === 'action' ||
      entry.mode === 'decision' ||
      entry.mode === 'success' ||
      entry.mode === 'escalation'
        ? entry.mode
        : undefined,
    actionMode:
      entry.actionMode === 'manual' ||
      entry.actionMode === 'confirm' ||
      entry.actionMode === 'automatic'
        ? entry.actionMode
        : undefined,
    actionResult:
      entry.actionResult === 'ok' || entry.actionResult === 'not_ok'
        ? entry.actionResult
        : undefined,
    nodeId: optionalString(entry.nodeId),
    taskId: optionalString(entry.taskId),
    from: optionalString(entry.from),
    action: optionalString(entry.action),
    time: optionalString(entry.time),
    next: entry.next,
    selectedFlowIds: Array.isArray(entry.selectedFlowIds)
      ? entry.selectedFlowIds.filter((id): id is string => typeof id === 'string')
      : undefined,
    reason: entry.reason,
    target: entry.target,
    previousResult: entry.previousResult,
    clearedResults: entry.clearedResults,
    inputChanges: entry.inputChanges,
    inputs: entry.inputs,
    evidence: entry.evidence,
    instructions: parseInstructions(entry.instructions),
  }))
}

export function useExecution(modeler: Modeler, visible: Ref<boolean>) {
  const runId = ref('')
  const snapshot = shallowRef<ExecutionHistory>()
  const nodes = ref<ExecutionNode[]>([])
  const connectionError = ref('')
  const loading = ref(false)
  const canvasMatches = ref(true)
  const canvas = modeler.get<Canvas>('canvas')
  const registry = modeler.get<ElementRegistry>('elementRegistry')
  const eventBus = modeler.get<EventBus>('eventBus')
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  let requestSequence = 0
  let revision = 0
  let disposed = false
  const markers = new Map<string, string>()
  const variables = computed<Record<string, unknown>>(() =>
    Object.fromEntries(
      (snapshot.value?.variables.data || []).flatMap(({ variable }) =>
        variable?.name ? [[variable.name, variable.value]] : [],
      ),
    ),
  )
  const pendingReviews = computed(
    () =>
      snapshot.value?.pendingReviews ??
      (snapshot.value?.review.pending ? [snapshot.value.review] : []),
  )
  const status = computed<ExecutionStatus>(() => {
    if (!snapshot.value) return 'loading'
    if (pendingReviews.value.length) return 'waiting'
    if (variables.value.diagnosticStatus === 'failed' || snapshot.value.failures?.length)
      return 'failed'
    if (variables.value.diagnosticStatus === 'paused') return 'paused'
    if (snapshot.value.process.endTime) return 'ended'
    return 'running'
  })
  // 并行支路仍可能继续运行；deadletter 只表示异常，不能代表引擎实例已结束。
  const terminal = computed(() => Boolean(snapshot.value?.process.endTime))
  const traces = computed(() =>
    Object.entries(variables.value).flatMap(([name, value]) => {
      if (!name.startsWith('executionTrace_')) return []
      const trace = parseTrace(value)
      return trace ? [trace] : []
    }),
  )
  const reviews = computed(() => parseReviews(variables.value.diagnosticReviews))
  const nodeViews = computed<ExecutionNodeView[]>(() =>
    nodes.value.map((node) => {
      // 同一节点可能有并行或重复执行记录；仍有活动未结束时不能显示完成。
      const occurrences = (snapshot.value?.activities.data || [])
        .filter((activity) => activity.activityId === node.id)
        .map((activity, index) => ({ activity, index }))
        .sort((a, b) => {
          const delta =
            Date.parse(a.activity.startTime || '') - Date.parse(b.activity.startTime || '')
          return Number.isFinite(delta) && delta !== 0 ? delta : a.index - b.index
        })
        .map(({ activity }) => activity)
      let state: ExecutionNodeStatus = occurrences.some((activity) => !activity.endTime)
        ? 'active'
        : occurrences.length
          ? 'completed'
          : 'idle'
      if (snapshot.value?.failures?.some((failure) => failure.activityId === node.id))
        state = 'failed'
      if (pendingReviews.value.some((review) => review.nodeId === node.id)) state = 'waiting'
      return {
        ...node,
        status: state,
        occurrences,
        hasResult: Object.prototype.hasOwnProperty.call(variables.value, node.id),
        result: variables.value[node.id],
        traces: traces.value.filter((trace) => trace.nodeId === node.id),
        // 旧协议的 from 就是来源节点；缺少来源的人工记录不能猜测归属。
        reviews: reviews.value.filter((review) => (review.nodeId || review.from) === node.id),
      }
    }),
  )
  function clearMarkers() {
    markers.forEach((marker, id) => {
      if (registry.get(id)) canvas.removeMarker(id, marker)
    })
    markers.clear()
  }
  function renderMarkers() {
    clearMarkers()
    if (!canvasMatches.value) return
    nodeViews.value.forEach((node) => {
      if (node.status === 'idle' || !registry.get(node.id)) return
      const marker = `execution-${node.status}`
      canvas.addMarker(node.id, marker)
      markers.set(node.id, marker)
    })
  }
  function stop() {
    if (timer) clearTimeout(timer)
    timer = undefined
    generation++
    loading.value = false
  }
  function schedule() {
    if (timer) clearTimeout(timer)
    timer = undefined
    if (disposed || !runId.value || terminal.value) return
    timer = setTimeout(() => void load(), 1500)
  }
  async function load() {
    if (!runId.value || disposed || loading.value) return
    if (timer) clearTimeout(timer)
    timer = undefined
    const id = runId.value
    const token = generation
    const sequence = ++requestSequence
    loading.value = true
    try {
      const result = await flowableRequest<ExecutionHistory>(`history/${encodeURIComponent(id)}`)
      if (disposed || token !== generation || id !== runId.value || sequence !== requestSequence)
        return
      snapshot.value = result
      connectionError.value = ''
      renderMarkers()
    } catch (error) {
      if (token !== generation || id !== runId.value || sequence !== requestSequence) return
      connectionError.value = error instanceof Error ? error.message : String(error)
    } finally {
      if (token === generation && sequence === requestSequence && !disposed) {
        loading.value = false
        schedule()
      }
    }
  }
  function capture() {
    return {
      revision,
      nodes: registry
        .getAll()
        .filter((element) => !element.labelTarget && is(element, 'bpmn:FlowNode'))
        .map((element) => ({
          id: element.id,
          name: getBusinessObject(element).name || element.id,
        })),
    }
  }
  function begin(id: string, captured: ReturnType<typeof capture>) {
    stop()
    clearMarkers()
    runId.value = id
    snapshot.value = undefined
    connectionError.value = ''
    nodes.value = captured.nodes
    canvasMatches.value = revision === captured.revision
  }
  async function reloadAfterReview() {
    stop()
    // 保留其余并行任务的窗口实例和草稿，直到最新快照替换旧状态。
    await load()
  }
  function changed() {
    revision++
    if (!runId.value) return
    canvasMatches.value = false
    clearMarkers()
  }
  const changeEvents = ['commandStack.changed', 'import.parse.start', 'diagram.clear']
  eventBus.on(changeEvents, changed)
  watch(visible, (opened) => {
    if (opened) {
      renderMarkers()
      void load()
    }
  })
  onBeforeUnmount(() => {
    disposed = true
    stop()
    clearMarkers()
    eventBus.off(changeEvents, changed)
  })
  return {
    runId,
    snapshot,
    pendingReviews,
    variables,
    status,
    terminal,
    nodeViews,
    canvasMatches,
    connectionError,
    loading,
    capture,
    begin,
    load,
    reloadAfterReview,
  }
}
