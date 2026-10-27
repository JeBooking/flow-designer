import type { Ref } from 'vue'
import type Modeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import type ElementRegistry from 'diagram-js/lib/core/ElementRegistry'
import type EventBus from 'diagram-js/lib/core/EventBus'
import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import { flowableRequest } from '@/services/flowable'
import type {
  ExecutionHistory,
  ExecutionNode,
  ExecutionNodeStatus,
  ExecutionNodeView,
  ExecutionStatus,
} from '@/types/flowableExecution'

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
  const status = computed<ExecutionStatus>(() => {
    if (!snapshot.value) return 'loading'
    if (snapshot.value.review.pending) return 'waiting'
    if (variables.value.diagnosticStatus === 'failed' || snapshot.value.failures?.length)
      return 'failed'
    if (variables.value.diagnosticStatus === 'paused') return 'paused'
    if (snapshot.value.process.endTime) return 'ended'
    return 'running'
  })
  // 并行支路仍可能继续运行；deadletter 只表示异常，不能代表引擎实例已结束。
  const terminal = computed(() => Boolean(snapshot.value?.process.endTime))
  const nodeViews = computed<ExecutionNodeView[]>(() =>
    nodes.value.map((node) => {
      // 引擎可能返回同一节点的多轮记录；仅最新一轮决定当前标记，完整经过保留供查看。
      const occurrences = (snapshot.value?.activities.data || [])
        .filter((activity) => activity.activityId === node.id)
        .map((activity, index) => ({ activity, index }))
        .sort((a, b) => {
          const delta =
            Date.parse(a.activity.startTime || '') - Date.parse(b.activity.startTime || '')
          return Number.isFinite(delta) && delta !== 0 ? delta : a.index - b.index
        })
        .map(({ activity }) => activity)
      const latest = occurrences[occurrences.length - 1]
      let state: ExecutionNodeStatus = latest?.endTime
        ? 'completed'
        : latest?.startTime
          ? 'active'
          : 'idle'
      if (snapshot.value?.failures?.some((failure) => failure.activityId === node.id))
        state = 'failed'
      if (snapshot.value?.review.pending && snapshot.value.review.nodeId === node.id)
        state = 'waiting'
      return {
        ...node,
        status: state,
        occurrences,
        hasResult: Object.prototype.hasOwnProperty.call(variables.value, node.id),
        result: variables.value[node.id],
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
    if (!visible.value || !canvasMatches.value) return
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
    if (disposed || !visible.value || !runId.value || terminal.value) return
    timer = setTimeout(() => void load(), 1500)
  }
  async function load() {
    if (!runId.value || disposed || !visible.value || loading.value) return
    if (timer) clearTimeout(timer)
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
    snapshot.value = undefined
    connectionError.value = ''
    clearMarkers()
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
    } else {
      stop()
      clearMarkers()
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
