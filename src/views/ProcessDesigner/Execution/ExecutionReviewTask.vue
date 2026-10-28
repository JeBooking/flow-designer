<script setup lang="ts">
import type { DiagnosisReviewState } from '@/types/diagnosis'
import { flowableRequest } from '@/services/flowable'
import ExecutionReviewForm from '@/views/ProcessDesigner/Execution/ExecutionReviewForm.vue'

const props = withDefaults(
  defineProps<{
    runId: string
    review: DiagnosisReviewState
    connected: boolean
    inputs?: unknown
    showHeading?: boolean
  }>(),
  { showHeading: true },
)
const emit = defineEmits<{ submitted: [taskId: string]; refresh: [] }>()
const target = ref('')
const reason = ref('')
const variables = ref('{}')
const next = ref('')
const selectedFlowIds = ref<string[]>([])
const busy = ref(false)
const errorMessage = ref('')
const completed = ref(false)
const lastActionResult = ref<'ok' | 'not_ok'>()
interface ReviewDraft {
  target: string
  reason: string
  variables: string
  next: string
  selectedFlowIds: string[]
  lastActionResult?: 'ok' | 'not_ok'
}
const drafts = new Map<string, ReviewDraft>()
let activeDraftKey = ''
let generation = 0
let disposed = false
const disabled = computed(
  () => busy.value || completed.value || !props.connected || !props.review.pending,
)
watch(
  [() => props.runId, () => props.review.taskId],
  () => {
    if (activeDraftKey)
      drafts.set(activeDraftKey, {
        target: target.value,
        reason: reason.value,
        variables: variables.value,
        next: next.value,
        selectedFlowIds: [...selectedFlowIds.value],
        lastActionResult: lastActionResult.value,
      })
    activeDraftKey = JSON.stringify([props.runId, props.review.taskId])
    const draft = drafts.get(activeDraftKey)
    generation++
    busy.value = false
    target.value = draft?.target || ''
    reason.value = draft?.reason || ''
    variables.value = draft?.variables || '{}'
    next.value =
      draft?.next ??
      (props.review.mode === 'action'
        ? props.review.lastActionResult || ''
        : props.review.options?.length === 1
          ? props.review.options[0].id
          : '')
    selectedFlowIds.value = draft?.selectedFlowIds || []
    lastActionResult.value = draft?.lastActionResult
    errorMessage.value = ''
    completed.value = false
  },
  { immediate: true, flush: 'sync' },
)
onBeforeUnmount(() => {
  disposed = true
  generation++
})
async function submit(action: 'recheck' | 'confirm', successAction?: 'continue' | 'finish') {
  if (disabled.value) return
  const submittedRunId = props.runId
  const submittedTaskId = props.review.taskId
  const token = generation
  errorMessage.value = ''
  if (!submittedRunId || !submittedTaskId) {
    errorMessage.value = translateUi(
      '人工任务已变化，请刷新状态',
      'The human task has changed. Refresh its status.',
    )
    emit('refresh')
    return
  }
  busy.value = true
  let requestStarted = false
  try {
    if (action === 'recheck' && props.review.canRecheck === false) {
      throw new Error(
        translateUi(
          '还有其他待处理任务，请先处理后再回退',
          'Resolve the other pending tasks before rechecking',
        ),
      )
    }
    const selectedNext = successAction || next.value
    const isAction = props.review.mode === 'action'
    if (action === 'confirm' && isAction && !['ok', 'not_ok'].includes(selectedNext))
      throw new Error(
        translateUi('请选择执行结果 OK 或不OK', 'Choose the action result: OK or Not OK'),
      )
    const option = isAction
      ? undefined
      : props.review.options?.find((entry) => entry.id === selectedNext)
    if (action === 'confirm' && props.review.mode === 'decision' && !option) {
      throw new Error(translateUi('请选择判断结果', 'Choose a decision'))
    }
    const paths = option?.paths
    const flowIds = paths
      ?.filter((path) => selectedFlowIds.value.includes(path.id))
      .map((path) => path.id)
    if (action === 'confirm' && paths?.length && !flowIds?.length) {
      throw new Error(translateUi('请至少选择一条后续路径', 'Select at least one next path'))
    }
    if (action === 'recheck' && (!target.value || !reason.value.trim())) {
      throw new Error(
        translateUi('请选择回退节点并填写原因', 'Select a recheck node and provide a reason'),
      )
    }
    if (
      action === 'recheck' &&
      !props.review.candidates?.some((entry) => entry.id === target.value)
    ) {
      throw new Error(
        translateUi('回退节点已变化，请重新选择', 'The recheck node has changed. Select it again.'),
      )
    }
    let inputVariables: unknown = {}
    if (action === 'recheck') {
      try {
        inputVariables = JSON.parse(variables.value)
      } catch {
        throw new Error(
          translateUi('复查输入变量必须是有效 JSON', 'Updated input variables must be valid JSON'),
        )
      }
      if (!inputVariables || typeof inputVariables !== 'object' || Array.isArray(inputVariables)) {
        throw new Error(translateUi('变量必须是 JSON 对象', 'Variables must be a JSON object'))
      }
    }
    // 确认期间仍会轮询；将输入与任务身份一起捕获，不能发送新任务或后续编辑的数据。
    const payload = {
      action,
      taskId: submittedTaskId,
      targetNodeId: target.value,
      reason: reason.value,
      variables: inputVariables,
      next: selectedNext,
      ...(action === 'confirm' && paths !== undefined ? { selectedFlowIds: flowIds } : {}),
    }
    if (action === 'recheck') {
      await ElMessageBox.confirm(
        translateUi(
          '将重新执行选中节点及后续逻辑，可能再次执行机台动作。原记录保留，但不会撤销已经执行的动作。',
          'The selected node and downstream logic will run again, including possible machine actions. Previous records are retained; completed actions are not undone.',
        ),
        translateUi('回退重查', 'Recheck an earlier node'),
        { type: 'warning' },
      )
    }
    if (
      disposed ||
      token !== generation ||
      submittedRunId !== props.runId ||
      submittedTaskId !== props.review.taskId ||
      !props.review.pending ||
      (action === 'recheck' && props.review.canRecheck === false) ||
      !props.connected
    ) {
      if (!disposed) emit('refresh')
      throw new Error(
        translateUi(
          '人工任务或连接已变化，本次操作未提交，请查看最新状态',
          'The human task or connection has changed. This action was not submitted. Check the latest status.',
        ),
      )
    }
    requestStarted = true
    const result = await flowableRequest<{
      ok: boolean
      pending?: boolean
      actionResult?: 'ok' | 'not_ok'
    }>('review/' + encodeURIComponent(submittedRunId), payload)
    if (disposed || token !== generation) return
    if (isAction && action === 'confirm' && result.pending === true) {
      lastActionResult.value = result.actionResult
      emit('refresh')
      return
    }
    if (isAction && action === 'confirm' && result.pending !== false)
      throw new Error(
        translateUi(
          '未收到任务完成确认，请刷新状态后重试',
          'Task completion was not confirmed. Refresh the status before retrying.',
        ),
      )
    completed.value = true
    emit('submitted', submittedTaskId)
  } catch (failure) {
    if (disposed || token !== generation || failure === 'cancel' || failure === 'close') return
    errorMessage.value = failure instanceof Error ? failure.message : String(failure)
    // 服务错误也可能表示任务已被其他窗口完成；刷新状态但绝不自动重发。
    if (requestStarted) emit('refresh')
  } finally {
    if (!disposed && token === generation) busy.value = false
  }
}
</script>

<template>
  <section class="review-task" :aria-busy="busy">
    <el-alert
      v-if="!connected"
      type="warning"
      :closable="false"
      show-icon
      :title="
        $tu(
          '连接已中断，恢复连接后可操作',
          'Connection lost. Actions are available after reconnecting.',
        )
      "
    />
    <p v-if="busy" role="status">{{ $tu('正在提交此任务…', 'Submitting this task…') }}</p>
    <el-alert v-if="errorMessage" type="error" :title="errorMessage" :closable="false" show-icon />
    <el-alert
      v-if="review.mode === 'action' && (lastActionResult || review.lastActionResult) === 'not_ok'"
      type="warning"
      :closable="false"
      show-icon
      :title="
        $tu(
          '执行结果未通过，任务仍在等待。请在现场完成或重做后提交 OK，或回退重查；平台不会自动重复调用接口。',
          'The action was not verified and this task is still waiting. Complete or redo it on site, then submit OK, or recheck an earlier node. The platform will not automatically repeat the interface call.',
        )
      "
    />
    <el-alert
      v-if="completed"
      type="success"
      :closable="false"
      :title="$tu('操作已提交，正在更新执行状态', 'Action submitted. Updating execution status.')"
    />
    <ExecutionReviewForm
      v-model:target="target"
      v-model:reason="reason"
      v-model:variables="variables"
      v-model:next="next"
      v-model:selected-flow-ids="selectedFlowIds"
      :review="review"
      :inputs="inputs"
      :show-heading="showHeading"
      :disabled="disabled"
      @submit="submit"
    />
  </section>
</template>

<style scoped>
.review-task {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.review-task > p {
  margin: 0;
  color: var(--el-text-color-secondary);
}
</style>
