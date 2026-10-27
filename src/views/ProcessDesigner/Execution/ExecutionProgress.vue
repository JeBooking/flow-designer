<script setup lang="ts">
import type {
  ExecutionNodeView,
  ExecutionNodeStatus,
  ExecutionStatus,
} from '@/types/flowableExecution'
import ExecutionValue from '@/views/ProcessDesigner/Execution/ExecutionValue.vue'
defineProps<{
  status: ExecutionStatus
  nodes: ExecutionNodeView[]
  connectionError: string
  canvasMatches: boolean
  loading: boolean
}>()
const labels = computed<Record<ExecutionStatus, string>>(() => ({
  loading: translateUi('正在读取执行状态', 'Loading execution status'),
  running: translateUi('正在执行', 'Running'),
  waiting: translateUi('等待人工复核', 'Awaiting human review'),
  paused: translateUi('诊断已暂停', 'Diagnosis paused'),
  failed: translateUi('执行异常／诊断失败', 'Execution error / diagnosis failed'),
  ended: translateUi('流程已结束', 'Process ended'),
}))
const nodeLabels = computed<Record<ExecutionNodeStatus, string>>(() => ({
  idle: translateUi('未执行', 'Not visited'),
  active: translateUi('执行中', 'Running'),
  completed: translateUi('已执行', 'Completed'),
  waiting: translateUi('等待复核', 'Awaiting review'),
  failed: translateUi('执行异常', 'Failed'),
}))
const tagType = (status: ExecutionNodeStatus) =>
  (
    ({
      idle: 'info',
      active: 'primary',
      completed: 'success',
      waiting: 'warning',
      failed: 'danger',
    }) as const
  )[status]
</script>

<template>
  <section class="progress-panel">
    <div role="status" aria-live="polite" aria-atomic="true" class="status-heading">
      <strong>{{ labels[status] }}</strong>
      <span v-if="connectionError">
        ·
        {{
          $tu(
            '连接中断，将自动重试；保留上次状态',
            'Connection interrupted; retrying automatically. Last known state retained',
          )
        }}</span
      >
    </div>
    <p v-if="connectionError" class="connection-error">{{ connectionError }}</p>
    <p v-else-if="loading" class="muted">{{ $tu('正在更新…', 'Updating…') }}</p>
    <p v-if="!canvasMatches" class="muted">
      {{
        $tu(
          '画布已修改，已隐藏高亮。下列记录仍对应启动时的流程。',
          'The canvas has changed; highlights are hidden. These records refer to the diagram at execution start.',
        )
      }}
    </p>
    <div class="legend" :aria-label="$tu('节点状态图例', 'Node status legend')">
      <el-tag
        v-for="state in ['active', 'waiting', 'completed', 'failed', 'idle'] as const"
        :key="state"
        :type="tagType(state)"
        size="small"
        >{{ nodeLabels[state] }}</el-tag
      >
    </div>
    <ol class="node-list">
      <li v-for="node in nodes" :key="node.id">
        <div class="node-heading">
          <strong>{{ node.name }}</strong
          ><el-tag :type="tagType(node.status)" size="small">{{ nodeLabels[node.status] }}</el-tag>
        </div>
        <div class="muted">{{ node.id }}</div>
        <ExecutionValue v-if="node.hasResult" :value="node.result" class="node-result" />
        <p v-else-if="node.status !== 'idle'" class="muted">
          {{ $tu('暂无返回结果', 'No result returned yet') }}
        </p>
        <details v-if="node.occurrences.length">
          <summary>
            {{ $tu('执行经过', 'Execution occurrences') }} ({{ node.occurrences.length }})
          </summary>
          <ol class="occurrences">
            <li v-for="(activity, index) in node.occurrences" :key="activity.id || index">
              {{ activity.startTime || '—' }} → {{ activity.endTime || $tu('执行中', 'Running') }}
              <span v-if="activity.durationInMillis != null">
                · {{ activity.durationInMillis }} ms</span
              >
            </li>
          </ol>
        </details>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.progress-panel {
  margin-block: 20px;
}
.status-heading {
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background: var(--el-fill-color-light);
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-block: 14px;
}
.node-list {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 12px;
}
.node-list > li {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 14px;
  min-width: 0;
}
.node-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  overflow-wrap: anywhere;
}
.node-result {
  margin-block: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.connection-error {
  color: var(--el-color-danger);
  overflow-wrap: anywhere;
}
.occurrences {
  padding-left: 20px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
summary {
  cursor: pointer;
  margin-top: 8px;
}
</style>
