<script setup lang="ts">
import type { DiagnosisReviewState } from '@/types/diagnosis'
import ExecutionValue from '@/views/ProcessDesigner/Execution/ExecutionValue.vue'
import ReferenceFile from '@/views/ProcessDesigner/Panel/Investigation/ReferenceFile.vue'

const props = withDefaults(
  defineProps<{
    review: DiagnosisReviewState
    disabled: boolean
    inputs?: unknown
    showHeading?: boolean
  }>(),
  { showHeading: true },
)
const emit = defineEmits<{
  submit: [action: 'recheck' | 'confirm', successAction?: 'continue' | 'finish']
}>()
const target = defineModel<string>('target', { required: true })
const reason = defineModel<string>('reason', { required: true })
const variables = defineModel<string>('variables', { required: true })
const next = defineModel<string>('next', { required: true })
const selectedFlowIds = defineModel<string[]>('selectedFlowIds', { default: () => [] })
const selectedOption = computed(() =>
  props.review.options?.find((option) => option.id === next.value),
)
const reviewInputs = computed(() => props.review.inputs ?? props.inputs)
// 切换判断分组时重置为该组全部路径，避免携带另一分组的连线。
watch(
  [
    () => props.review.taskId,
    () => next.value,
    () => selectedOption.value?.paths?.map((path) => path.id).join('\n'),
  ],
  () => {
    selectedFlowIds.value = selectedOption.value?.paths?.map((path) => path.id) || []
  },
  { immediate: true, flush: 'sync' },
)
const decisionPending = computed(() => props.review.mode === 'decision')
const successPending = computed(() => props.review.mode === 'success')
const reviewInstructions = computed(() =>
  [
    { label: translateUi('详细内容', 'Details'), value: props.review.instructions?.detailText },
    {
      label: translateUi('查看什么数据', 'Data to inspect'),
      value: props.review.instructions?.observation,
    },
    {
      label: translateUi('如何获取数据', 'How to acquire data'),
      value: props.review.instructions?.acquisition,
    },
    {
      label: translateUi('判断方法', 'Assessment method'),
      value: props.review.instructions?.assessment,
    },
    {
      label: translateUi('结论内容', 'Conclusion'),
      value: props.review.instructions?.conclusionText,
    },
    { label: translateUi('动作内容', 'Action'), value: props.review.instructions?.actionText },
  ].filter((item) => item.value),
)
</script>

<template>
  <section class="review-form" :aria-busy="disabled">
    <header v-if="showHeading" class="review-heading">
      <strong>{{ review.name || review.nodeId }}</strong>
      <code>{{ review.nodeId }}</code>
    </header>
    <template v-for="instruction in reviewInstructions" :key="instruction.label">
      <p>
        <strong>{{ instruction.label }}</strong>
      </p>
      <p class="execution-results">{{ instruction.value }}</p>
    </template>
    <ReferenceFile
      v-if="review.instructions?.referenceImage"
      :value="review.instructions.referenceImage"
      :name="review.instructions.referenceImageName"
      readonly
    />
    <section v-if="review.evidence != null" class="review-evidence">
      <h4>{{ $tu('实际判断依据', 'Actual decision evidence') }}</h4>
      <ExecutionValue :value="review.evidence" />
    </section>
    <details v-if="reviewInputs != null">
      <summary>{{ $tu('人工复核上下文', 'Human review context') }}</summary>
      <ExecutionValue :value="reviewInputs" />
    </details>
    <el-form v-if="decisionPending" label-position="top" :disabled="disabled">
      <el-form-item
        v-if="review.options?.length"
        :label="$tu('选择判断结果', 'Choose the decision')"
      >
        <el-radio-group v-model="next" class="review-options" :disabled="disabled">
          <el-radio v-for="option in review.options" :key="option.id" :value="option.id" border>
            <strong>{{ option.name }}</strong>
            <span v-if="option.paths?.length" class="option-paths">
              {{ option.paths.map((path) => path.name || path.target).join(' / ') }}
            </span>
            <span v-else-if="option.paths" class="option-paths">
              {{
                $tu(
                  '此结果没有后续路径，将记录该思路失败。',
                  'This result has no next path; this investigation path will be recorded as failed.',
                )
              }}
            </span>
          </el-radio>
        </el-radio-group>
      </el-form-item>
      <div v-if="selectedOption?.paths?.length" class="review-paths">
        <h4>{{ $tu('即将执行', 'Next to execute') }}</h4>
        <template v-if="selectedOption.paths.length > 1">
          <p>
            {{
              $tu(
                '默认执行全部路径，也可选择其中部分。',
                'All paths are selected by default. You may choose a subset.',
              )
            }}
          </p>
          <el-checkbox-group v-model="selectedFlowIds" :disabled="disabled">
            <el-checkbox v-for="path in selectedOption.paths" :key="path.id" :value="path.id">
              {{ path.name || path.target }}
            </el-checkbox>
          </el-checkbox-group>
        </template>
        <p v-else>{{ selectedOption.paths[0].name || selectedOption.paths[0].target }}</p>
      </div>
    </el-form>
    <details v-if="!successPending" class="review-recheck">
      <summary>{{ $tu('回退重查（高级操作）', 'Recheck an earlier node (advanced)') }}</summary>
      <p v-if="review.canRecheck === false" role="status">
        {{
          $tu(
            '还有其他待处理任务，请先处理后再回退',
            'Resolve the other pending tasks before rechecking',
          )
        }}
      </p>
      <p v-if="!review.candidates?.length">
        {{ $tu('尚无此前已执行的节点可供回退。', 'No earlier executed nodes are available yet.') }}
      </p>
      <el-form label-position="top" :disabled="disabled || review.canRecheck === false">
        <el-form-item :label="$tu('回退到此前已执行的节点', 'Return to an earlier executed node')">
          <el-select v-model="target" style="width: 100%">
            <el-option
              v-for="candidate in review.candidates || []"
              :key="candidate.id"
              :value="candidate.id"
              :label="`${candidate.name} (${candidate.id})`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$tu('回退原因', 'Recheck reason')">
          <el-input v-model="reason" type="textarea" :rows="2" />
        </el-form-item>
        <details class="review-json">
          <summary>
            {{ $tu('复查输入变量 JSON（可选）', 'Updated input variables JSON (optional)') }}
          </summary>
          <el-form-item :label="$tu('复查输入变量（可选）', 'Updated input variables (optional)')">
            <el-input v-model="variables" type="textarea" :rows="3" />
          </el-form-item>
        </details>
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
          :disabled="disabled || review.canRecheck === false || !review.candidates?.length"
          @click="emit('submit', 'recheck')"
          >{{ $tu('回退重查', 'Recheck') }}</el-button
        >
      </el-space>
    </details>
    <footer class="review-actions">
      <template v-if="successPending">
        <el-button type="primary" :disabled="disabled" @click="emit('submit', 'confirm', 'finish')">
          {{ $tu('结束本轮排查', 'Finish this investigation') }}
        </el-button>
        <el-button :disabled="disabled" @click="emit('submit', 'confirm', 'continue')">
          {{ $tu('继续排查其余思路', 'Continue remaining paths') }}
        </el-button>
      </template>
      <el-button v-else type="primary" :disabled="disabled" @click="emit('submit', 'confirm')">
        {{
          decisionPending
            ? $tu('确认并继续', 'Confirm and continue')
            : $tu('确认上升并结束本轮排查', 'Confirm escalation and finish this investigation')
        }}
      </el-button>
    </footer>
  </section>
</template>

<style scoped>
.review-form {
  overflow-wrap: anywhere;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--el-text-color-primary);
  line-height: 1.6;
}
.review-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.review-heading code,
.option-paths {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.review-form p,
.review-form h4 {
  margin: 0;
}
.review-form summary {
  cursor: pointer;
  padding-block: 8px;
}
.review-evidence,
.review-paths {
  padding: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
}
.review-options,
.review-paths :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: 100%;
}
.review-options :deep(.el-radio) {
  height: auto;
  min-height: 48px;
  margin-right: 0;
  padding: 12px;
}
.review-options :deep(.el-radio__label),
.review-paths :deep(.el-checkbox__label) {
  white-space: normal;
  overflow-wrap: anywhere;
}
.option-paths {
  display: block;
  padding-top: 4px;
}
.review-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-block: 16px;
  border-top: 1px solid var(--el-border-color-light);
}
.review-actions :deep(.el-button) {
  margin-left: 0;
  white-space: normal;
  height: auto;
  min-height: 36px;
}
.execution-results {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
