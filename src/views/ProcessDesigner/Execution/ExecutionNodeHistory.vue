<script setup lang="ts">
import type { ExecutionNodeView, ExecutionReview, ExecutionTrace } from '@/types/flowableExecution'
import ExecutionValue from '@/views/ProcessDesigner/Execution/ExecutionValue.vue'
import ExecutionTraceDetails from '@/views/ProcessDesigner/Execution/ExecutionTraceDetails.vue'
import { translateUi } from '@/languages/uiText'

const props = defineProps<{ node: ExecutionNodeView }>()
type HistoryRecord =
  | { key: string; time: string; kind: 'trace'; trace: ExecutionTrace }
  | { key: string; time: string; kind: 'review'; review: ExecutionReview }
const records = computed<HistoryRecord[]>(() => {
  const traces: HistoryRecord[] = (props.node.traces || []).map((trace) => ({
    key: `${props.node.id}:trace:${trace.id}`,
    time: trace.startedAt,
    kind: 'trace',
    trace,
  }))
  const reviews: HistoryRecord[] = (props.node.reviews || []).map((review, index) => ({
    key: `${props.node.id}:review:${index}`,
    time: review.time || '',
    kind: 'review',
    review,
  }))
  // 调用记录和引擎活动没有一一对应关系，只按各自记录时间展示。
  return [...traces, ...reviews].sort((a, b) => {
    const first = Date.parse(a.time)
    const second = Date.parse(b.time)
    if (!Number.isFinite(first)) return Number.isFinite(second) ? -1 : 0
    return Number.isFinite(second) ? first - second : 1
  })
})
const opened = ref<Record<string, boolean>>({})
const latestOpen = ref(false)
const isOpen = (key: string, index: number) =>
  opened.value[key] ?? index === records.value.length - 1
function toggleRecord(key: string, event: Event) {
  if (event.target instanceof HTMLDetailsElement) opened.value[key] = event.target.open
}
const traceStatus = (status: ExecutionTrace['status']) => {
  if (status === 'completed') return translateUi('已完成', 'Completed')
  if (status === 'waiting') return translateUi('等待人工处理', 'Waiting for human review')
  return translateUi('失败', 'Failed')
}
</script>

<template>
  <section class="node-history">
    <p>
      <strong>{{ node.name }}</strong> ({{ node.id }})
    </p>
    <h4>{{ $tu('逐次处理记录', 'Individual processing records') }} ({{ records.length }})</h4>
    <p v-if="!records.length" class="history-note">
      {{
        $tu(
          '此实例未采集该节点的逐次调用或人工处理记录。',
          'This instance did not collect individual call or human review records for this node.',
        )
      }}
    </p>
    <details
      v-for="(record, index) in records"
      :key="record.key"
      class="history-record"
      :open="isOpen(record.key, index)"
      @toggle="toggleRecord(record.key, $event)"
    >
      <summary>
        <strong>{{
          record.kind === 'trace'
            ? $tu('模块调用记录', 'Module call record')
            : $tu('人工处理记录', 'Human review record')
        }}</strong>
        <span>{{ record.time || $tu('时间未记录', 'Time not recorded') }}</span>
        <el-tag
          v-if="record.kind === 'trace'"
          size="small"
          :type="
            record.trace.status === 'failed'
              ? 'danger'
              : record.trace.status === 'waiting'
                ? 'warning'
                : 'success'
          "
        >
          {{ traceStatus(record.trace.status) }}
        </el-tag>
      </summary>
      <template v-if="isOpen(record.key, index)">
        <p v-if="record.kind === 'trace'" class="history-note">
          {{ $tu('结束', 'Ended') }}: {{ record.trace.endedAt || $tu('未记录', 'Not recorded') }}
        </p>
        <ExecutionTraceDetails
          :trace="record.kind === 'trace' ? record.trace : undefined"
          :review="record.kind === 'review' ? record.review : undefined"
        />
      </template>
    </details>
    <details class="activity-history">
      <summary>
        {{ $tu('引擎活动时间（辅助信息）', 'Engine activity times (supporting information)') }} ({{
          node.occurrences.length
        }})
      </summary>
      <p class="history-note">
        {{
          $tu(
            '引擎活动与模块调用不一定一一对应，以下时间不用于推断调用参数或输出。',
            'Engine activities and module calls do not necessarily correspond one to one. These times do not imply call arguments or outputs.',
          )
        }}
      </p>
      <ol v-if="node.occurrences.length">
        <li v-for="(activity, index) in node.occurrences" :key="activity.id || index">
          <p>{{ $tu('开始', 'Started') }}: {{ activity.startTime || '—' }}</p>
          <p>{{ $tu('结束', 'Ended') }}: {{ activity.endTime || $tu('执行中', 'Running') }}</p>
          <p>
            {{ $tu('耗时', 'Duration') }}:
            {{ activity.durationInMillis != null ? activity.durationInMillis + ' ms' : '—' }}
          </p>
        </li>
      </ol>
      <p v-else>{{ $tu('暂无执行记录', 'No execution records yet') }}</p>
    </details>
    <details
      class="activity-history"
      @toggle="latestOpen = ($event.target as HTMLDetailsElement).open"
    >
      <summary>{{ $tu('当前最新结果', 'Latest current result') }}</summary>
      <p class="history-note">
        {{
          $tu(
            '仅表示当前保存的节点值，不代表任何历史轮次的结果。',
            'This is only the currently saved node value, not the result of any historical occurrence.',
          )
        }}
      </p>
      <template v-if="latestOpen">
        <ExecutionValue v-if="node.hasResult" :value="node.result" />
        <p v-else>{{ $tu('暂无返回结果', 'No result returned yet') }}</p>
      </template>
    </details>
  </section>
</template>

<style scoped>
.node-history {
  overflow-wrap: anywhere;
}
.history-record,
.activity-history {
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
  padding: 12px;
  margin: 12px 0;
}
summary {
  cursor: pointer;
  line-height: 1.8;
}
summary span,
summary .el-tag {
  margin-left: 8px;
}
summary:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: 4px;
}
ol {
  padding-left: 24px;
}
li {
  border-bottom: 1px solid var(--el-border-color-light);
}
.history-note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
