<script setup lang="ts">
import { getDiagnosisKind, getDiagnosisBranch } from '@/views/ProcessDesigner/Diagnosis/model'
import type EventBus from 'diagram-js/lib/core/EventBus'
import type { Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import { getBusinessObject, is } from 'bpmn-js/lib/util/ModelUtil'
import { useBpmnContextService } from '@/hooks/useService.ts'
import type Modeling from 'bpmn-js/lib/features/modeling/Modeling'
import type BpmnFactory from 'bpmn-js/lib/features/modeling/BpmnFactory'
import { createElement, isConditionalSource } from '@/views/ProcessDesigner/utils/ElementUtil.ts'
import Codemirror from '@/components/CodemirrorEditor/index.vue'
import juelSupport from '@/components/CodemirrorEditor/language/juel'

defineOptions({
  name: 'SequenceFlow',
})
const { updateProperties, selectedElement, getService } = useBpmnContextService()
const eventBus = getService<EventBus>('eventBus')!
const revision = ref(0)
const refresh = () => revision.value++
eventBus.on('elements.changed', refresh)
onBeforeUnmount(() => eventBus.off('elements.changed', refresh))
const isInvestigationBranch = computed(() => {
  void revision.value
  return getDiagnosisKind(selectedElement?.source) === 'investigation'
})
const branch = computed({
  get: () => {
    void revision.value
    return selectedElement ? getDiagnosisBranch(selectedElement) : undefined
  },
  set: (value) => updateProperties({ 'flowable:diagnosisBranch': value }),
})
const isSerial = computed(() => {
  void revision.value
  let scope: ModdleElement | undefined = getBusinessObject(selectedElement)
  while (scope && !is(scope, 'bpmn:Process')) scope = scope.$parent
  return scope?.get('flowable:diagnosisMode') === 'serial'
})
const executionOrder = computed<number | null>({
  get: () => {
    void revision.value
    return getBusinessObject(selectedElement).get('flowable:diagnosisOrder') ?? null
  },
  set: (value) => {
    if (value !== null && !Number.isSafeInteger(value)) return
    updateProperties({ 'flowable:diagnosisOrder': value ?? undefined })
  },
})
const modeling = getService<Modeling>('modeling')
const bpmnFactory = getService<BpmnFactory>('bpmnFactory')
const conditionExpression = customRef<string>((track, trigger) => {
  return {
    get() {
      track()
      const businessObject = getBusinessObject(selectedElement)
      if (businessObject.conditionExpression) {
        return businessObject.conditionExpression.body
      }
    },
    set(newValue?: string) {
      if (bpmnFactory && selectedElement) {
        const conditionExpression = createElement(
          'bpmn:FormalExpression',
          bpmnFactory,
          {
            body: newValue,
          },
          selectedElement,
        )
        updateCondition(conditionExpression)
      }
      trigger()
    },
  }
})

const circulationType = customRef<string>((track, trigger) => {
  return {
    get() {
      track()
      if (selectedElement) {
        const businessObject = getBusinessObject(selectedElement)
        if (businessObject.conditionExpression) {
          return 'conditional'
        } else if (isConditionalSource(selectedElement.source)) {
          const business = getBusinessObject(selectedElement.source)
          if (business.default?.id === selectedElement.id) {
            return 'default'
          }
        }
      }
      return 'none'
    },
    set(newValue: string) {
      if (!selectedElement) return
      if (newValue === 'none') {
        setDefaultCondition(selectedElement, false)
        updateCondition(undefined)
      } else if (newValue === 'conditional') {
        if (selectedElement.source.businessObject.default?.id === selectedElement.id) {
          setDefaultCondition(selectedElement, false)
        }
        conditionExpression.value = ``
      } else if (newValue === 'default') {
        setDefaultCondition(selectedElement, true)
        updateCondition(undefined)
      }
      trigger()
    },
  }
})
const setDefaultCondition = (element: Element, isDefault: boolean) => {
  const { source } = element
  if (isConditionalSource(source)) {
    modeling?.updateProperties(source, { default: isDefault ? element : undefined })
  }
}

const updateCondition = (condition?: Element) => {
  updateProperties({
    conditionExpression: condition,
  })
}
</script>

<template>
  <el-collapse-item
    v-if="isInvestigationBranch"
    name="arg1"
    :title="$tu('判断分支', 'Decision branch')"
  >
    <el-form-item :label="$tu('判断结果', 'Decision result')" required>
      <el-radio-group v-model="branch">
        <el-radio-button value="yes" :label="$tu('是', 'Yes')" />
        <el-radio-button value="no" :label="$tu('否', 'No')" />
      </el-radio-group>
    </el-form-item>
    <el-form-item v-if="isSerial" :label="$tu('执行顺序', 'Execution order')">
      <el-input-number
        v-model="executionOrder"
        :precision="0"
        :step="1"
        :min="0"
        :max="2147483647"
        :value-on-clear="null"
        :aria-label="$tu('执行顺序', 'Execution order')"
        :placeholder="$tu('按连线顺序', 'Connection order')"
        controls-position="right"
      />
    </el-form-item>
    <p class="branch-help">
      {{
        isSerial
          ? $tu(
              '同一结果可以连接多个节点，也可以只配置一种结果。串行模式按执行顺序从小到大运行；未填写时按连线顺序，相同序号保持原顺序。',
              'Either result can have any number of connections, and one result may be omitted. Serial mode runs in ascending order; unset values use connection order, and ties keep the original order.',
            )
          : $tu(
              '同一结果可以连接多个节点，也可以只配置一种结果。并行模式下，所有匹配连线同时生效，没有优先级。',
              'Either result can have any number of connections, and one result may be omitted. Parallel mode runs all matching branches without priority.',
            )
      }}
    </p>
    <p class="branch-help">
      {{
        $tu(
          '画布连线名称仅支持是、否、yes、no，英文不区分大小写。',
          'Canvas connection names accept only 是, 否, yes, or no, case-insensitively.',
        )
      }}
    </p>
  </el-collapse-item>
  <el-collapse-item v-else name="arg1" :title="$tu('流转条件')">
    <el-form-item prop="type" :label="$tu('流转类型')">
      <el-radio-group v-model="circulationType">
        <el-radio-button :label="$tu('普通')" value="none" />
        <el-radio-button :label="$tu('默认')" value="default" />
        <el-radio-button :label="$tu('条件')" value="conditional" />
      </el-radio-group>
    </el-form-item>
    <el-form-item v-if="circulationType === 'conditional'" :label="$tu('条件表达式')">
      <Codemirror
        :rows="3"
        :max-rows="6"
        autosize
        no-wrap
        :placeholder="$tu('请输入条件表达式')"
        :extensions="[juelSupport()]"
        v-model="conditionExpression"
      />
      <!--      <el-input
        v-model="conditionExpression"
        :placeholder="$tu('请输入条件表达式')"
        type="textarea"
        :rows="3"
      />-->
    </el-form-item>
  </el-collapse-item>
</template>

<style scoped lang="scss">
.branch-help {
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin: 0 0 12px;
}
</style>
