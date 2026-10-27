<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type ElementRegistry from 'diagram-js/lib/core/ElementRegistry'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type Overlays from 'diagram-js/lib/features/overlays/Overlays'
import type { ExecutionNodeView } from '@/types/flowableExecution'

const props = defineProps<{
  modeler: BpmnModeler
  nodes: ExecutionNodeView[]
  runId: string
  enabled: boolean
}>()
const emit = defineEmits<{ select: [nodeId: string] }>()

interface NodeOverlay {
  overlayId: string
  host: HTMLDivElement
  node: ExecutionNodeView
}

const entries = shallowRef<NodeOverlay[]>([])
const overlaysByNode = new Map<string, NodeOverlay>()
let overlays: Overlays | undefined
let registry: ElementRegistry | undefined
let eventBus: EventBus | undefined
let disposed = false

function clearOverlays() {
  for (const entry of overlaysByNode.values()) overlays?.remove(entry.overlayId)
  overlaysByNode.clear()
  entries.value = []
}

function syncOverlays() {
  if (disposed || !overlays || !registry) return
  if (!props.enabled) {
    clearOverlays()
    return
  }

  const visibleNodes = new Map(
    props.nodes
      .filter(
        (node) =>
          (node.status === 'waiting' || node.status === 'completed') && registry?.get(node.id),
      )
      .map((node) => [node.id, node]),
  )

  for (const [nodeId, entry] of overlaysByNode) {
    if (!visibleNodes.has(nodeId) || !overlays.get(entry.overlayId)) {
      overlays.remove(entry.overlayId)
      overlaysByNode.delete(nodeId)
    }
  }

  for (const [nodeId, node] of visibleNodes) {
    const existing = overlaysByNode.get(nodeId)
    if (existing) {
      // 保留宿主和按钮实例，轮询更新不能打断键盘焦点。
      existing.node = node
      continue
    }
    const host = document.createElement('div')
    const overlayId = overlays.add(nodeId, 'execution-node-action', {
      position: { top: -28, right: 12 },
      html: host,
      scale: { min: 1, max: 1 },
    })
    overlaysByNode.set(nodeId, { overlayId, host, node })
  }
  entries.value = [...overlaysByNode.values()]
}

function scheduleSync() {
  // 删除事件期间注册表和覆盖层尚未全部更新，等待本轮画布操作结束。
  void nextTick(syncOverlays)
}

const canvasEvents = ['import.done', 'elements.changed', 'shape.removed']

function detachModeler() {
  eventBus?.off(canvasEvents, scheduleSync)
  eventBus?.off('diagram.clear', clearOverlays)
  clearOverlays()
}

watch(
  () => props.modeler,
  (modeler) => {
    detachModeler()
    overlays = modeler.get<Overlays>('overlays')
    registry = modeler.get<ElementRegistry>('elementRegistry')
    eventBus = modeler.get<EventBus>('eventBus')
    eventBus.on(canvasEvents, scheduleSync)
    eventBus.on('diagram.clear', clearOverlays)
    syncOverlays()
  },
  { immediate: true },
)
watch(() => props.runId, clearOverlays, { flush: 'sync' })
watch(() => props.enabled, syncOverlays, { flush: 'sync' })
watch(() => [props.nodes, props.runId], syncOverlays)

function actionLabel(node: ExecutionNodeView) {
  const name = node.name || node.id
  return node.status === 'waiting'
    ? translateUi(`${name}：待处理，打开节点操作`, `${name}: action required, open node actions`)
    : translateUi(`${name}：已完成，查看结果`, `${name}: completed, view results`)
}

onBeforeUnmount(() => {
  disposed = true
  detachModeler()
})
</script>

<template>
  <Teleport v-for="entry in entries" :key="entry.overlayId" :to="entry.host">
    <button
      type="button"
      class="execution-node-action"
      :class="`execution-node-action--${entry.node.status}`"
      :aria-label="actionLabel(entry.node)"
      :title="actionLabel(entry.node)"
      @pointerdown.stop
      @mousedown.stop
      @dblclick.stop
      @keydown.stop
      @keyup.stop
      @click.stop="emit('select', entry.node.id)"
    >
      <svg
        v-if="entry.node.status === 'completed'"
        viewBox="0 0 24 24"
        aria-hidden="true"
        class="execution-node-action__icon"
      >
        <path d="m5 12 4 4L19 6" />
      </svg>
      <span v-else class="execution-node-action__attention" aria-hidden="true">!</span>
      <span>
        {{
          entry.node.status === 'waiting'
            ? $tu('待处理', 'Action required')
            : $tu('已完成', 'Completed')
        }}
      </span>
    </button>
  </Teleport>
</template>

<style scoped lang="scss">
.execution-node-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 44px;
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid var(--el-color-warning);
  border-radius: 8px;
  background: var(--el-color-warning-light-9);
  color: var(--el-color-warning-dark-2);
  box-shadow: 0 2px 6px rgb(15 23 42 / 12%);
  font: 600 12px/1.3 var(--el-font-family, sans-serif);
  white-space: nowrap;
  cursor: pointer;

  &:hover {
    background: var(--el-color-warning-light-8);
  }

  &:focus-visible {
    outline: 3px solid var(--el-color-primary);
    outline-offset: 3px;
  }

  &--completed {
    border-color: var(--el-color-success);
    background: var(--el-color-success-light-9);
    color: var(--el-color-success-dark-2);

    &:hover {
      background: var(--el-color-success-light-8);
    }
  }

  &__icon {
    width: 18px;
    height: 18px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  &__attention {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border: 1.5px solid currentColor;
    border-radius: 50%;
  }
}
</style>
