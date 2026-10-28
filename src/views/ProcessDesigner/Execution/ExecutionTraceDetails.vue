<script setup lang="ts">
import type { ExecutionReview, ExecutionTrace } from '@/types/flowableExecution'
import ExecutionValue from '@/views/ProcessDesigner/Execution/ExecutionValue.vue'
import ReferenceFile from '@/views/ProcessDesigner/Panel/Investigation/ReferenceFile.vue'
import { translateUi } from '@/languages/uiText'

const props = defineProps<{ trace?: ExecutionTrace; review?: ExecutionReview }>()
const record = computed(() => props.trace || props.review)
const instructions = computed(() => record.value?.instructions)
const instructionFields = computed(() =>
  [
    [translateUi('观察项', 'Observation'), instructions.value?.observation],
    [translateUi('采集说明', 'Acquisition instructions'), instructions.value?.acquisition],
    [translateUi('判断说明', 'Assessment instructions'), instructions.value?.assessment],
    [translateUi('详细说明', 'Details'), instructions.value?.detailText],
    [translateUi('结论说明', 'Conclusion instructions'), instructions.value?.conclusionText],
    [translateUi('处置说明', 'Action instructions'), instructions.value?.actionText],
  ].filter(([, value]) => value !== undefined && value !== ''),
)
const reviewFields = computed(() => [
  ...(props.review?.mode === 'action' || props.review?.actionResult || props.review?.actionMode
    ? [
        [
          translateUi('执行结果', 'Action result'),
          props.review.actionResult === 'ok'
            ? 'OK'
            : props.review.actionResult === 'not_ok'
              ? translateUi('不OK', 'Not OK')
              : undefined,
        ],
        [
          translateUi('执行方式', 'Execution mode'),
          props.review.actionMode === 'manual'
            ? translateUi('人工执行并确认', 'Perform manually and confirm')
            : props.review.actionMode === 'confirm'
              ? translateUi('接口执行后人工核验', 'Run interface, then verify manually')
              : props.review.actionMode === 'automatic'
                ? translateUi('自动执行', 'Automatic execution')
                : undefined,
        ],
      ]
    : []),
  [translateUi('选择动作', 'Selected action'), props.review?.action],
  ...(props.review?.mode === 'action'
    ? []
    : [[translateUi('后续节点', 'Next node'), props.review?.next]]),
  ...(props.review?.mode === 'action'
    ? []
    : [[translateUi('选择的后续路径', 'Selected next paths'), props.review?.selectedFlowIds]]),
  [translateUi('目标节点', 'Target node'), props.review?.target],
  [translateUi('原因', 'Reason'), props.review?.reason],
  [translateUi('处理前结果', 'Previous result'), props.review?.previousResult],
  [translateUi('清除的结果', 'Cleared results'), props.review?.clearedResults],
  [translateUi('输入修改', 'Input changes'), props.review?.inputChanges],
])
const callFields = computed(() => {
  const call = props.trace?.call
  return call
    ? Object.fromEntries(Object.entries(call).filter(([, value]) => value !== undefined))
    : undefined
})
</script>

<template>
  <div class="trace-details">
    <p v-if="trace" class="metadata">
      {{ $tu('记录标识', 'Record ID') }}: {{ trace.id }}
      <template v-if="trace.jobId"> · {{ $tu('作业', 'Job') }}: {{ trace.jobId }}</template>
    </p>
    <p v-if="review?.taskId" class="metadata">
      {{ $tu('人工任务', 'Human task') }}: {{ review.taskId }}
    </p>
    <section v-if="trace?.call">
      <h5>{{ $tu('调用信息', 'Call information') }}</h5>
      <ExecutionValue :value="callFields" />
    </section>
    <section>
      <h5>
        {{
          trace
            ? $tu('本次调用输入', 'Inputs for this call')
            : $tu('当时上下文输入', 'Context inputs at the time')
        }}
      </h5>
      <p v-if="review" class="metadata">
        {{
          $tu(
            '人工处理时的业务上下文，不代表函数调用参数。',
            'Business context at the time of human review; these are not function call arguments.',
          )
        }}
      </p>
      <ExecutionValue v-if="record?.inputs !== undefined" :value="record.inputs" />
      <p v-else class="metadata">{{ $tu('未记录', 'Not recorded') }}</p>
    </section>
    <section v-if="trace && Object.prototype.hasOwnProperty.call(trace, 'factoryInputs')">
      <h5>{{ $tu('实例初始化输入', 'Instance initialization inputs') }}</h5>
      <ExecutionValue :value="trace.factoryInputs" />
    </section>
    <section>
      <h5>{{ $tu('判断依据数据', 'Evidence data') }}</h5>
      <ExecutionValue v-if="record?.evidence !== undefined" :value="record.evidence" />
      <p v-else class="metadata">{{ $tu('未记录', 'Not recorded') }}</p>
    </section>
    <section>
      <h5>{{ $tu('参考说明与文件', 'Reference instructions and file') }}</h5>
      <dl v-if="instructionFields.length">
        <template v-for="[label, value] in instructionFields" :key="label">
          <dt>{{ label }}</dt>
          <dd>{{ value }}</dd>
        </template>
      </dl>
      <p v-else class="metadata">
        {{ $tu('参考说明未记录', 'Reference instructions not recorded') }}
      </p>
      <ReferenceFile
        v-if="instructions?.referenceImage"
        :value="instructions.referenceImage"
        :name="instructions.referenceImageName"
        readonly
      />
      <p v-else class="metadata">{{ $tu('参考文件未记录', 'Reference file not recorded') }}</p>
      <template v-if="trace?.judgmentInstructions !== undefined">
        <h5>{{ $tu('本次判断说明', 'Judgment instructions for this call') }}</h5>
        <p>{{ trace.judgmentInstructions }}</p>
      </template>
    </section>
    <section v-if="trace">
      <h5>{{ $tu('本次结果', 'Result for this call') }}</h5>
      <ExecutionValue v-if="trace.result !== undefined" :value="trace.result" />
      <p v-else class="metadata">{{ $tu('未记录', 'Not recorded') }}</p>
      <h5>{{ $tu('分支记录', 'Recorded route') }}</h5>
      <ExecutionValue v-if="trace.route !== undefined" :value="trace.route" />
      <p v-else class="metadata">{{ $tu('未记录', 'Not recorded') }}</p>
    </section>
    <section v-if="review">
      <h5>{{ $tu('人工选择与处理结果', 'Human choice and review outcome') }}</h5>
      <dl>
        <template v-for="[label, value] in reviewFields" :key="String(label)">
          <dt>{{ label }}</dt>
          <dd>
            <ExecutionValue v-if="value !== undefined" :value="value" />
            <span v-else class="metadata">{{ $tu('未记录', 'Not recorded') }}</span>
          </dd>
        </template>
      </dl>
    </section>
    <section v-if="trace?.error !== undefined || trace?.traceback">
      <h5>{{ $tu('错误详情', 'Error details') }}</h5>
      <ExecutionValue v-if="trace.error !== undefined" :value="trace.error" />
      <details v-if="trace.traceback">
        <summary>{{ $tu('查看错误堆栈', 'View traceback') }}</summary>
        <pre>{{ trace.traceback }}</pre>
      </details>
    </section>
  </div>
</template>

<style scoped>
.trace-details {
  display: grid;
  gap: 16px;
  padding: 12px 0;
}
h5 {
  margin: 0 0 8px;
  font-size: 14px;
}
p {
  margin: 8px 0;
  white-space: pre-wrap;
}
.metadata {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
dl {
  display: grid;
  grid-template-columns: minmax(80px, 1fr) minmax(0, 3fr);
  gap: 8px 12px;
  margin: 0;
}
dt {
  color: var(--el-text-color-secondary);
}
dd {
  margin: 0;
  white-space: pre-wrap;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
summary {
  cursor: pointer;
}
</style>
