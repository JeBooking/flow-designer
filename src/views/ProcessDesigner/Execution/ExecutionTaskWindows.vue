<script setup lang="ts">
import type BpmnModeler from 'bpmn-js/lib/Modeler'
import type Canvas from 'diagram-js/lib/core/Canvas'
import type ElementRegistry from 'diagram-js/lib/core/ElementRegistry'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type { ElementLike, ShapeLike } from 'diagram-js/lib/model/Types'
import type { CSSProperties } from 'vue'
import type { DiagnosisReviewState } from '@/types/diagnosis'
import {
  clampWindow,
  placeTaskWindow,
  rectEdge,
  type TaskRect,
} from '@/views/ProcessDesigner/Execution/taskWindowLayout'

const props = defineProps<{
  modeler: BpmnModeler
  runId: string
  reviews: DiagnosisReviewState[]
  enabled: boolean
}>()

interface TaskWindow {
  id: string
  review: DiagnosisReviewState
  rect: TaskRect
  anchor: TaskRect
  collapsed: boolean
  pinned: boolean
  placed: boolean
  outside: boolean
  order: number
  layoutOrder: number
  measuredWidth?: number
  measuredHeight?: number
}

const entries = ref<TaskWindow[]>([])
const container = shallowRef<HTMLElement>()
const viewport = reactive({ width: 0, height: 0 })
const narrow = computed(() => viewport.width < 680)
const cardElements = new Map<string, HTMLElement>()
const cardRefs = new Map<string, (element: unknown) => void>()
let canvas: Canvas | undefined
let registry: ElementRegistry | undefined
let eventBus: EventBus | undefined
let observer: ResizeObserver | undefined
let frame = 0
let order = 0
let disposed = false
const drag = shallowRef<{ id: string; pointer: number; x: number; y: number; start: TaskRect }>()

const events = ['canvas.viewbox.changed', 'canvas.resized', 'elements.changed', 'import.done']

function invalidateAutomaticLayout() {
  for (const entry of entries.value) {
    if (!entry.pinned && !entry.collapsed) entry.placed = false
  }
}

function isShape(element: ElementLike | undefined): element is ShapeLike {
  return (
    !!element &&
    typeof element.x === 'number' &&
    typeof element.y === 'number' &&
    typeof element.width === 'number' &&
    typeof element.height === 'number'
  )
}

function scheduleSync() {
  if (frame || disposed) return
  frame = requestAnimationFrame(() => {
    frame = 0
    syncGeometry()
  })
}

function syncGeometry() {
  if (!container.value || !canvas || !registry) return
  let layoutChanged =
    viewport.width !== container.value.clientWidth ||
    viewport.height !== container.value.clientHeight
  viewport.width = container.value.clientWidth
  viewport.height = container.value.clientHeight
  const width = Math.max(160, Math.min(380, viewport.width - 16))
  const height = Math.max(80, Math.min(520, viewport.height - 76))
  for (const entry of entries.value) {
    const shape = entry.review.nodeId ? registry.get(entry.review.nodeId) : undefined
    const box = isShape(shape) ? canvas.getAbsoluteBBox(shape) : undefined
    entry.outside =
      !box ||
      box.x + box.width < 0 ||
      box.y + box.height < 0 ||
      box.x > viewport.width ||
      box.y > viewport.height
    entry.anchor = box
      ? { x: box.x, y: box.y, width: box.width, height: box.height }
      : { x: viewport.width / 2, y: 60, width: 1, height: 1 }
    const card = cardElements.get(entry.id)
    const cardHeight = card?.offsetHeight || Math.min(entry.rect.height, height)
    if (card && !entry.collapsed && card.offsetWidth && card.offsetHeight) {
      if (entry.measuredWidth !== card.offsetWidth || entry.measuredHeight !== card.offsetHeight) {
        layoutChanged = true
        entry.measuredWidth = card.offsetWidth
        entry.measuredHeight = card.offsetHeight
      }
    }
    entry.rect = clampWindow(
      { ...entry.rect, width, height: Math.min(cardHeight, height) },
      viewport.width,
      viewport.height,
    )
  }
  if (layoutChanged) invalidateAutomaticLayout()
  const nodes = entries.value.map((entry) => entry.anchor)
  // 固定窗口先占位，自动窗口按首次出现顺序放置，轮询的数组顺序不影响布局。
  const occupied = entries.value
    .filter((entry) => !entry.collapsed && (entry.pinned || entry.placed))
    .map((entry) => entry.rect)
  const automatic = entries.value
    .filter((entry) => !entry.pinned && !entry.collapsed)
    .sort((a, b) => a.layoutOrder - b.layoutOrder)
  for (const entry of automatic) {
    if (entry.placed || narrow.value) continue
    entry.rect = placeTaskWindow(entry.anchor, entry.rect, occupied, nodes, viewport)
    entry.placed = true
    occupied.push(entry.rect)
  }
}

function reconcile() {
  if (!props.enabled || !container.value) return
  const current = new Map(entries.value.map((entry) => [entry.id, entry]))
  const reviews = new Map(
    props.reviews
      .filter((review) => review.pending && review.taskId)
      .map((review) => [review.taskId!, review]),
  )
  const tasksChanged =
    current.size !== reviews.size || [...reviews.keys()].some((id) => !current.has(id))
  // 同一任务的轮询结果复用窗口，避免表单、滚动位置和手动布局被重建。
  entries.value = [...reviews.values()].map((review) => {
    const id = review.taskId!
    const existing = current.get(id)
    if (existing) {
      existing.review = review
      return existing
    }
    return {
      id,
      review,
      rect: { x: 8, y: 60, width: 380, height: 330 },
      anchor: { x: 8, y: 60, width: 1, height: 1 },
      collapsed: false,
      pinned: false,
      placed: false,
      outside: false,
      order: ++order,
      layoutOrder: order,
    }
  })
  if (tasksChanged) invalidateAutomaticLayout()
  syncGeometry()
  void nextTick(scheduleSync)
}

function setCard(id: string, element: unknown) {
  const previous = cardElements.get(id)
  if (previous === element) return
  if (previous) observer?.unobserve(previous)
  if (element instanceof HTMLElement) {
    cardElements.set(id, element)
    observer?.observe(element)
  } else cardElements.delete(id)
}

function cardRef(id: string) {
  let callback = cardRefs.get(id)
  if (!callback) {
    callback = (element: unknown) => setCard(id, element)
    cardRefs.set(id, callback)
  }
  return callback
}

function clearWindows() {
  drag.value = undefined
  entries.value = []
  for (const element of cardElements.values()) observer?.unobserve(element)
  cardElements.clear()
  cardRefs.clear()
}

function detach() {
  eventBus?.off(events, scheduleSync)
  eventBus?.off('diagram.clear', clearWindows)
  container.value?.removeEventListener('scroll', scheduleSync, true)
  window.removeEventListener('resize', scheduleSync)
  window.removeEventListener('pointermove', moveDrag)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
  observer?.disconnect()
  observer = undefined
  if (frame) cancelAnimationFrame(frame)
  frame = 0
  clearWindows()
  container.value = undefined
  canvas = undefined
  registry = undefined
  eventBus = undefined
}

function attach() {
  detach()
  if (!props.enabled || disposed) return
  canvas = props.modeler.get<Canvas>('canvas')
  registry = props.modeler.get<ElementRegistry>('elementRegistry')
  eventBus = props.modeler.get<EventBus>('eventBus')
  container.value = canvas.getContainer()
  eventBus.on(events, scheduleSync)
  eventBus.on('diagram.clear', clearWindows)
  container.value.addEventListener('scroll', scheduleSync, true)
  window.addEventListener('resize', scheduleSync)
  window.addEventListener('pointermove', moveDrag)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
  observer = new ResizeObserver(scheduleSync)
  observer.observe(container.value)
  reconcile()
}

function open(taskId: string) {
  const entry = entries.value.find((item) => item.id === taskId)
  if (!entry) return
  const wasCollapsed = entry.collapsed
  entry.collapsed = false
  if (wasCollapsed) {
    invalidateAutomaticLayout()
    scheduleSync()
  }
  entry.order = ++order
  void nextTick(() => {
    const card = cardElements.get(taskId)
    if (narrow.value) card?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    card?.querySelector<HTMLElement>('.task-window__handle')?.focus({ preventScroll: true })
    scheduleSync()
  })
}

function collapse(entry: TaskWindow) {
  entry.collapsed = true
  invalidateAutomaticLayout()
  scheduleSync()
}

function arrange() {
  for (const entry of entries.value) {
    entry.pinned = false
    entry.placed = false
  }
  syncGeometry()
}

function automatic(entry: TaskWindow) {
  entry.pinned = false
  entry.placed = false
  syncGeometry()
}

function startDrag(event: PointerEvent, entry: TaskWindow) {
  event.stopPropagation()
  if (event.button !== 0 || narrow.value) return
  event.preventDefault()
  entry.order = ++order
  drag.value = {
    id: entry.id,
    pointer: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    start: { ...entry.rect },
  }
}

function moveDrag(event: PointerEvent) {
  const active = drag.value
  if (!active || active.pointer !== event.pointerId) return
  const entry = entries.value.find((item) => item.id === active.id)
  if (!entry) return
  entry.pinned = true
  entry.rect = clampWindow(
    {
      ...entry.rect,
      x: active.start.x + event.clientX - active.x,
      y: active.start.y + event.clientY - active.y,
    },
    viewport.width,
    viewport.height,
  )
}

function stopDrag() {
  drag.value = undefined
}

function moveByKey(event: KeyboardEvent, entry: TaskWindow) {
  const directions: Record<string, [number, number]> = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }
  const direction = directions[event.key]
  if (!direction || narrow.value) return
  event.preventDefault()
  const distance = event.shiftKey ? 40 : 10
  entry.pinned = true
  entry.rect = clampWindow(
    {
      ...entry.rect,
      x: entry.rect.x + direction[0] * distance,
      y: entry.rect.y + direction[1] * distance,
    },
    viewport.width,
    viewport.height,
  )
}

function locate(entry: TaskWindow) {
  const shape = entry.review.nodeId ? registry?.get(entry.review.nodeId) : undefined
  if (!isShape(shape) || !canvas) return
  const box = canvas.getAbsoluteBBox(shape)
  canvas.scroll({
    dx: viewport.width / 2 - box.x - box.width / 2,
    dy: viewport.height / 2 - box.y - box.height / 2,
  })
  scheduleSync()
}

function cardStyle(entry: TaskWindow): CSSProperties {
  const anchor = rectEdge(entry.anchor, entry.rect)
  const x = Math.max(8, Math.min(anchor.x, viewport.width - 8))
  const y = Math.max(8, Math.min(anchor.y, viewport.height - 8))
  return {
    '--window-x': `${entry.rect.x}px`,
    '--window-y': `${entry.rect.y}px`,
    '--return-x': `${x - entry.rect.x}px`,
    '--return-y': `${y - entry.rect.y}px`,
    width: `${entry.rect.width}px`,
    maxHeight: `${Math.max(80, Math.min(520, viewport.height - 76))}px`,
    zIndex: entry.order,
  } as CSSProperties
}

function connector(entry: TaskWindow) {
  const end = rectEdge(entry.rect, {
    x: entry.anchor.x + entry.anchor.width / 2,
    y: entry.anchor.y + entry.anchor.height / 2,
  })
  const start = rectEdge(entry.anchor, end)
  start.x = Math.max(5, Math.min(start.x, viewport.width - 5))
  start.y = Math.max(5, Math.min(start.y, viewport.height - 5))
  const middle = (start.x + end.x) / 2
  return `M ${start.x} ${start.y} C ${middle} ${start.y}, ${middle} ${end.y}, ${end.x} ${end.y}`
}

watch(() => [props.modeler, props.enabled, props.runId], attach, { immediate: true })
watch(
  () => props.reviews.map((review) => [review, review.pending, review.taskId, review.nodeId]),
  reconcile,
)
onBeforeUnmount(() => {
  disposed = true
  detach()
})
defineExpose({ open, arrange })
</script>

<template>
  <Teleport v-if="container && enabled" :to="container">
    <div
      class="task-windows"
      :class="{ 'task-windows--narrow': narrow }"
      @mousedown.stop
      @dblclick.stop
      @keydown.stop
      @keyup.stop
    >
      <svg v-if="!narrow" class="task-windows__connections" aria-hidden="true">
        <TransitionGroup name="task-connector" tag="g">
          <path
            v-for="entry in entries.filter((item) => !item.collapsed)"
            :key="entry.id"
            :d="connector(entry)"
          />
        </TransitionGroup>
      </svg>
      <nav
        v-if="entries.length"
        class="task-windows__navigation"
        :aria-label="$tu('待办窗口', 'Pending task windows')"
        @wheel.stop
        @pointerdown.stop
      >
        <button type="button" @click="arrange">{{ $tu('自动排布', 'Arrange') }}</button>
        <button
          v-for="entry in entries"
          :key="entry.id"
          type="button"
          :aria-expanded="!entry.collapsed"
          @click="open(entry.id)"
        >
          {{ entry.review.name || entry.review.nodeId || entry.id }}
          <span v-if="entry.collapsed">{{ $tu('（已收起）', '(collapsed)') }}</span>
        </button>
      </nav>
      <TransitionGroup name="task-window" tag="div" class="task-windows__cards">
        <section
          v-for="entry in entries"
          v-show="!entry.collapsed"
          :key="entry.id"
          :ref="cardRef(entry.id)"
          class="task-window"
          :class="{ 'task-window--dragging': drag?.id === entry.id }"
          :style="cardStyle(entry)"
          :aria-label="entry.review.name || entry.review.nodeId || entry.id"
          @pointerdown.stop="entry.order = ++order"
          @wheel.stop
          @touchstart.stop
        >
          <header class="task-window__header">
            <button
              type="button"
              class="task-window__handle"
              :title="
                $tu(
                  '拖动或使用方向键移动，Shift 加速',
                  'Drag or use arrow keys to move; Shift moves faster',
                )
              "
              @pointerdown="startDrag($event, entry)"
              @keydown="moveByKey($event, entry)"
            >
              <span aria-hidden="true">⠿</span>
              <strong>{{ entry.review.name || entry.review.nodeId || entry.id }}</strong>
            </button>
            <button
              type="button"
              :aria-label="$tu('收起窗口', 'Collapse window')"
              @click="collapse(entry)"
            >
              −
            </button>
          </header>
          <div class="task-window__source">
            <button type="button" @click="locate(entry)">
              {{ $tu('来源节点：', 'Source node: ') }}{{ entry.review.nodeId || '—' }}
              <span v-if="entry.outside">{{ $tu('（画布外）', '(outside viewport)') }}</span>
            </button>
            <button v-if="entry.pinned" type="button" @click="automatic(entry)">
              {{ $tu('恢复自动', 'Unpin') }}
            </button>
          </div>
          <div class="task-window__body"><slot :review="entry.review" /></div>
        </section>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped lang="scss">
.task-windows {
  position: absolute;
  inset: 0;
  z-index: 20;
  overflow: hidden;
  pointer-events: none;
  color: var(--el-text-color-primary);
  font: 14px/1.5 var(--el-font-family, sans-serif);

  button {
    min-height: 44px;
    min-width: 44px;
    padding: 6px 10px;
    border: 0;
    border-radius: 5px;
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
    &:hover {
      background: var(--el-fill-color);
    }
    &:focus-visible {
      outline: 2px solid var(--el-color-primary);
      outline-offset: -2px;
    }
  }
  &__connections {
    position: absolute;
    width: 100%;
    height: 100%;
    pointer-events: none;
    path {
      fill: none;
      stroke: var(--el-color-primary);
      stroke-width: 1.5;
      stroke-dasharray: 5 4;
    }
  }
  &__navigation {
    position: absolute;
    inset: 8px 8px auto;
    z-index: 2147483647;
    display: flex;
    gap: 8px;
    max-height: 44px;
    overflow: auto;
    pointer-events: auto;
    button {
      flex-shrink: 0;
      max-width: 240px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      border: 1px solid var(--el-border-color);
      background: var(--el-bg-color-overlay);
    }
  }
}
.task-window {
  box-sizing: border-box;
  position: absolute;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-bg-color-overlay);
  box-shadow: var(--el-box-shadow);
  pointer-events: auto;
  transform: translate(var(--window-x), var(--window-y));
  transition:
    transform 180ms ease,
    opacity 180ms ease;
  &--dragging {
    transition: none;
  }
  &__header {
    display: flex;
    flex-shrink: 0;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }
  &__handle {
    display: flex;
    flex: 1;
    align-items: center;
    gap: 8px;
    min-width: 0 !important;
    text-align: left;
    touch-action: none;
    cursor: grab !important;
    strong {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
  &__source {
    display: flex;
    flex-shrink: 0;
    justify-content: space-between;
    flex-wrap: wrap;
    color: var(--el-text-color-secondary);
    font-size: 12px;
    button {
      overflow-wrap: anywhere;
      text-align: left;
    }
  }
  &__body {
    min-height: 0;
    padding: 12px;
    overflow: auto;
    overscroll-behavior: contain;
  }
  &-enter-from,
  &-leave-to {
    opacity: 0;
    transform: translate(
        calc(var(--window-x) + var(--return-x)),
        calc(var(--window-y) + var(--return-y))
      )
      scale(0.15);
    transform-origin: top left;
  }
  &-leave-active {
    pointer-events: none;
  }
}
.task-windows--narrow {
  .task-windows__cards {
    position: absolute;
    inset: 60px 8px 8px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    overscroll-behavior: contain;
    pointer-events: auto;
  }
  .task-window {
    position: relative;
    flex-shrink: 0;
    width: 100% !important;
    transform: none;
    &__handle {
      cursor: default !important;
      touch-action: auto;
    }
    &-enter-from,
    &-leave-to {
      transform: translateY(16px);
    }
  }
}
.task-connector-enter-active,
.task-connector-leave-active {
  transition: opacity 180ms ease;
}
.task-connector-enter-from,
.task-connector-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .task-window,
  .task-connector-enter-active,
  .task-connector-leave-active {
    transition: none;
  }
}
</style>
