<script setup lang="ts">
import { getDiagnosisKind, getDiagnosisBranch } from '@/views/ProcessDesigner/Diagnosis/model'
import type { Element } from 'bpmn-js/lib/model/Types'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
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
const isInvestigationBranch = computed(
  () => getDiagnosisKind(selectedElement?.source) === 'investigation',
)
const branch = computed({
  get: () => (selectedElement ? getDiagnosisBranch(selectedElement) : undefined),
  set: (value) =>
    updateProperties({
      'flowable:diagnosisBranch': value,
      name: value,
      conditionExpression: undefined,
    }),
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
    <p>
      {{
        $tu(
          '同一结果可以连接多个节点，所有连线同时生效，没有优先级。存在依赖时，请将后续节点连接在依赖节点之后。',
          'Connect multiple nodes to either result. All matching branches run without priority. Connect dependent nodes after their prerequisite.',
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

<style scoped lang="scss"></style>
