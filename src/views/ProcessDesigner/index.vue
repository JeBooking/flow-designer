<script setup lang="ts">
import 'bpmn-js/dist/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn.css'
import 'bpmn-js/dist/assets/bpmn-js.css'
import 'diagram-js-minimap/assets/diagram-js-minimap.css'
import 'bpmn-js-token-simulation/assets/css/bpmn-js-token-simulation.css'
import 'bpmn-js-bpmnlint/dist/assets/css/bpmn-js-bpmnlint.css'

import 'bpmn-js/dist/assets/bpmn-font/css/bpmn-embedded.css'
import 'bpmn-js-color-picker/colors/color-picker.css'
import ToggleMode from 'bpmn-js-token-simulation/lib/features/toggle-mode/modeler/ToggleMode'
import BpmnModeler from 'bpmn-js/lib/Modeler'
import {
  CaretLeft,
  CaretRight,
  Download,
  FolderOpened,
  Moon,
  Sunny,
  VideoPause,
  VideoPlay,
  ZoomIn,
  ZoomOut,
} from '@element-plus/icons-vue'
import type CommandStack from 'diagram-js/lib/command/CommandStack'
import BpmnPanel from './BpmnPanel.vue'
import BpmnDesigner from './BpmnModeler.tsx'
import EmptyXML from './EmptyXML'
import type { Injector } from 'didi'
import { getRootElement, nextId } from './utils/ElementUtil.ts'
import type { ElementIssue, Issues, Linting } from 'bpmn-js-bpmnlint'
import type Canvas from 'diagram-js/lib/core/Canvas'
import type { Minimap } from 'diagram-js-minimap'
import { layoutProcess } from 'bpmn-auto-layout'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import useAppStore from '@/stores/modules/app.ts'
import { generateProject } from '@/views/ProcessDesigner/CodeGeneration/generate'
import type { ModelElement } from '@/views/ProcessDesigner/CodeGeneration/generate'
import { createArchive } from '@/views/ProcessDesigner/CodeGeneration/archive'
import PythonProjects from '@/views/ProcessDesigner/PythonProjects.vue'
import FlowableExecution from '@/views/ProcessDesigner/FlowableExecution.vue'
import { importWorkflowJson } from '@/views/ProcessDesigner/CodeGeneration/importWorkflow'
import { generateWorkflowDefinition } from '@/views/ProcessDesigner/CodeGeneration/workflowDefinition'

defineOptions({
  name: 'ProcessDesigner',
})
const { language } = storeToRefs(useAppStore())
const { t } = useI18n()
const props = defineProps<{
  id?: string
  name?: string
  xml?: string
  idPrefix?: string
}>()
const mockVisible = customRef<boolean>((track, trigger) => {
  return {
    get() {
      track()
      const toggleMode = modeler.value?.get<ToggleMode>('toggleMode')
      return toggleMode?._active || false
    },
    set() {
      const toggleMode = modeler.value?.get<ToggleMode>('toggleMode')
      toggleMode?.toggleMode()
      trigger()
    },
  }
})
const lintVisible = customRef<boolean>((track, trigger) => {
  return {
    get() {
      track()
      const linting = injector.value?.get<Linting>('linting')
      return linting?.isActive() || false
    },
    set(newValue: boolean) {
      const linting = injector.value?.get<Linting>('linting')
      linting?.toggle(newValue)
      trigger()
    },
  }
})
const mapVisible = customRef<boolean>((track, trigger) => {
  return {
    get() {
      track()
      const minimap = modeler.value?.get<Minimap>('minimap')
      return minimap?.isOpen() || false
    },
    set(newValue: boolean) {
      const minimap = modeler.value?.get<Minimap>('minimap')
      minimap?.toggle(newValue)
      trigger()
    },
  }
})
let notifyZoomChanged: (() => void) | undefined
const zoom = customRef<number>((track, trigger) => {
  notifyZoomChanged = trigger
  return {
    get() {
      track()
      return modeler.value?.get<Canvas>('canvas')?.zoom() || 1
    },
    set(newValue: number) {
      modeler.value?.get<Canvas>('canvas')?.zoom(newValue)
      trigger()
    },
  }
})
const isDark = customRef<boolean>((track, trigger) => {
  return {
    get() {
      track()
      return document.documentElement.classList.contains('dark')
    },
    set(newValue: boolean) {
      if (newValue) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
      trigger()
    },
  }
})
const rightArrow = ref(true)
const issuesList = ref<ElementIssue[]>([])
const modeler = ref<BpmnModeler>()
const injector = ref<Injector>()
const fileRef = ref<HTMLInputElement>()
const pythonProjectsRef = ref<InstanceType<typeof PythonProjects>>()
const flowableRef = ref<InstanceType<typeof FlowableExecution>>()
const labelPosition = ref('left')
const formSize = ref('small')
const importing = ref(false)
const importXml = async () => {
  const file = fileRef.value?.files?.[0]
  if (!file || !modeler.value || importing.value) return
  importing.value = true
  try {
    const content = await file.text()
    const json = file.name.toLowerCase().endsWith('.json')
    const restored = json ? await importWorkflowJson(content) : undefined
    await modeler.value.importXML(restored?.xml ?? content)
    modeler.value.get<Canvas>('canvas').zoom('fit-viewport')
    if (restored) {
      ElNotification({
        type: restored.missingImages || restored.unclassifiedBranches ? 'warning' : 'success',
        title: translateUi('流程图已恢复', 'Workflow restored'),
        message:
          restored.missingImages || restored.unclassifiedBranches
            ? translateUi(
                `已恢复流程图并重新排版。${restored.missingImages} 张参考图需重新上传，${restored.unclassifiedBranches} 条排查连线需设置是／否类别；JSON 未记录的接口绑定需重新配置。`,
                `Workflow restored with a new layout. Upload ${restored.missingImages} reference images and assign Yes/No to ${restored.unclassifiedBranches} investigation connections. Configure interface bindings not recorded in the JSON.`,
              )
            : restored.portable
              ? translateUi(
                  '诊断定义已完整恢复，并自动生成布局。',
                  'Diagnostic definition restored with an automatically generated layout.',
                )
              : translateUi(
                  '已恢复节点、连线和排查模式并重新排版。JSON 未记录的接口绑定需重新配置。',
                  'Nodes, connections and investigation mode were restored with a new layout. Configure any interface bindings not recorded in the JSON.',
                ),
        duration: 0,
      })
    }
  } catch (error) {
    ElNotification.error({
      title: translateUi('流程导入失败', 'Workflow import failed'),
      message: error instanceof Error ? error.message : String(error),
      duration: 0,
    })
  } finally {
    importing.value = false
    if (fileRef.value) fileRef.value.value = ''
  }
}
const exportXml = async () => {
  const xml = await getXml()
  if (xml) {
    const rootElement = getRootElement()
    const blob = new Blob([xml], { type: 'text/xml' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${rootElement?.businessObject.get('name') || t('ui.anonymousProcess')}.bpmn20.xml`
    a.click()
    window.URL.revokeObjectURL(url)
  }
}
const exportingCode = ref(false)
const exportDefinition = () => {
  if (!modeler.value) return
  try {
    const json = generateWorkflowDefinition(
      modeler.value.getDefinitions() as unknown as ModelElement,
    )
    const url = URL.createObjectURL(new Blob([json], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'workflow.json'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    ElNotification.error({
      title: translateUi('诊断定义导出失败', 'Diagnostic definition export failed'),
      message: error instanceof Error ? error.message : String(error),
      duration: 0,
    })
  }
}
const exportCode = async () => {
  if (!modeler.value || exportingCode.value) return
  exportingCode.value = true
  try {
    const xml = await getXml()
    if (!xml) throw new Error(translateUi('无法读取流程', 'Unable to read the process'))
    const files = generateProject(modeler.value.getDefinitions() as unknown as ModelElement, xml)
    const url = URL.createObjectURL(createArchive(files))
    const link = document.createElement('a')
    link.href = url
    link.download = 'diagnostic-workflow-python.zip'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    ElMessage.success(
      translateUi(
        'Python 工程已导出，请解压后阅读 README.md',
        'Python project exported. Extract it and read README.md.',
      ),
    )
  } catch (error) {
    ElNotification.error({
      title: translateUi('代码导出失败', 'Code export failed'),
      message: error instanceof Error ? error.message : String(error),
      duration: 0,
    })
  } finally {
    exportingCode.value = false
  }
}
const exportSvg = () => {
  modeler.value?.saveSVG().then(({ svg }) => {
    const replacedSvg = svg
      .replace(/var\(--bjsl-fill-color\)/g, '#fff')
      .replace(/var\(--bjsl-stroke-color\)/g, '#000')
    const blob = new Blob([replacedSvg], { type: 'image/svg+xml' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${t('ui.anonymousProcess')}.svg`
    a.click()
    window.URL.revokeObjectURL(url)
  })
}
const redo = () => {
  modeler.value?.get<CommandStack>('commandStack').redo()
}
const undo = () => {
  modeler.value?.get<CommandStack>('commandStack').undo()
}
const layout = async () => {
  const xml = await getXml()
  if (xml) {
    const diagramWithLayoutXML = await layoutProcess(xml)
    modeler.value?.importXML(diagramWithLayoutXML)
  }
}
const restart = () => {
  modeler.value?.get<CommandStack>('commandStack').clear()
  const xml = EmptyXML(props.id || nextId('Process_'), props.name || t('ui.newProcess'))
  modeler.value?.importXML(props.xml || xml)
  modeler.value?.get<Canvas>('canvas')?.zoom('fit-viewport')
}
const loadXml = (xml: string) => {
  modeler.value?.importXML(xml)
}
const getXml = async () => {
  const res = await modeler.value?.saveXML({ format: true, preamble: true })
  return res?.xml
}
const modelerReady = async (bpmnModeler: BpmnModeler) => {
  modeler.value = bpmnModeler
  injector.value = bpmnModeler.get<Injector>('injector')
  bpmnModeler.on('canvas.viewbox.changed', () => notifyZoomChanged?.())
  modeler.value?.on<{ issues: Issues }>('linting.completed', ({ issues }) => {
    issuesList.value = Object.values(issues).flat()
  })
  restart()
  // await bpmnModeler.createDiagram()
}
const validate = async () => {
  const errors = issuesList.value.filter((issue) => issue.category === 'error')
  if (errors.length) {
    return errors
  }
  return []
}
const resetZoom = () => {
  zoom.value = 1
  modeler.value?.get<Canvas>('canvas')?.zoom('fit-viewport')
}
const toggleRightArrow = () => {
  if (mockVisible.value) {
    return ElMessage.warning(t('ui.exitSimulationFirst'))
  }
  rightArrow.value = !rightArrow.value
}
provide('ProcessDesigner', {
  modeler: modeler,
})
defineExpose({
  loadXml,
  getXml,
  validate,
})
</script>

<template>
  <el-container class="design-container">
    <PythonProjects ref="pythonProjectsRef" />
    <FlowableExecution v-if="modeler" ref="flowableRef" :modeler="modeler" />
    <input
      ref="fileRef"
      accept=".xml,.bpmn,.json"
      @change="importXml"
      style="display: none"
      type="file"
    />
    <el-header class="design-header">
      <el-text tag="b" :size="'large'">{{ $t('ui.title') }}</el-text>
      <el-space>
        <el-button @click="flowableRef?.open()">{{
          $tu('Flowable 执行', 'Flowable execution')
        }}</el-button>
        <el-button @click="pythonProjectsRef?.open()">
          {{ $tu('Python 项目', 'Python projects') }}
        </el-button>
        <el-switch
          inline-prompt
          :active-text="$t('ui.labelPositionTop')"
          :inactive-text="$t('ui.labelPositionLeft')"
          active-value="top"
          inactive-value="left"
          v-model="labelPosition"
        />
        <el-switch
          inline-prompt
          :active-text="$t('ui.formSizeDefault')"
          :inactive-text="$t('ui.formSizeCompact')"
          active-value="default"
          inactive-value="small"
          v-model="formSize"
        />
        <el-switch inline-prompt :active-icon="Moon" :inactive-icon="Sunny" v-model="isDark" />
        <el-switch
          v-model="language"
          inline-prompt
          :active-text="$tu('中')"
          inactive-text="EN"
          active-value="zh-CN"
          inactive-value="en-US"
          :aria-label="$t('ui.switchLanguage')"
        />
        <el-link
          underline="never"
          target="_blank"
          href="https://github.com/tsai996/vue-bpmn-designer"
        >
          <Iconify class="el-icon--left" icon="ri:github-fill" width="25px" />
        </el-link>
        <el-link
          underline="never"
          target="_blank"
          href="https://gitee.com/cai_xiao_feng/vue-bpmn-designer"
        >
          <Iconify class="el-icon--left" icon="ri:gitee-fill" width="25px" />
        </el-link>
      </el-space>
    </el-header>
    <el-container style="overflow-y: auto">
      <el-container style="position: relative">
        <el-header class="design-inner__header">
          <el-space :size="10">
            <el-button-group size="small">
              <el-tooltip placement="top" :content="$t('ui.import')">
                <el-button
                  :icon="FolderOpened"
                  :loading="importing"
                  :aria-label="$tu('导入 BPMN 或 workflow.json', 'Import BPMN or workflow.json')"
                  @click="fileRef?.click()"
                />
              </el-tooltip>
              <el-tooltip
                placement="top"
                :content="
                  $tu(
                    '导出完整 BPMN（含布局与样式）',
                    'Export complete BPMN with layout and styles',
                  )
                "
              >
                <el-button
                  :icon="Download"
                  size="small"
                  @click="exportXml"
                  :aria-label="
                    $tu(
                      '导出完整 BPMN（包含布局与样式）',
                      'Export complete BPMN with layout and styles',
                    )
                  "
                />
              </el-tooltip>
              <el-button @click="exportDefinition">{{
                $tu('导出诊断 JSON', 'Export diagnostic JSON')
              }}</el-button>
              <el-button :loading="exportingCode" @click="exportCode">
                {{ $tu('导出 Python 骨架', 'Export Python skeleton') }}
              </el-button>
            </el-button-group>

            <el-button-group size="small">
              <el-tooltip placement="top" :content="$t('ui.undo')">
                <el-button @click="undo">
                  <iconify icon="ic:baseline-undo" :size="3" />
                </el-button>
              </el-tooltip>
              <el-tooltip placement="top" :content="$t('ui.redo')">
                <el-button @click="redo">
                  <iconify icon="ic:baseline-redo" :size="3" />
                </el-button>
              </el-tooltip>
            </el-button-group>

            <el-button-group size="small">
              <el-tooltip :content="$t('ui.zoomIn')" placement="top-start">
                <el-button :icon="ZoomIn" @click="zoom += 0.1" :disabled="zoom >= 1.7"></el-button>
              </el-tooltip>
              <el-tooltip :content="$t('ui.resetZoom')" placement="top-start">
                <el-button @click="resetZoom"> {{ (zoom * 100).toFixed(0) }}%</el-button>
              </el-tooltip>
              <el-tooltip :content="$t('ui.zoomOut')" placement="top-start">
                <el-button :icon="ZoomOut" @click="zoom -= 0.1" :disabled="zoom <= 0.5"></el-button>
              </el-tooltip>
            </el-button-group>

            <el-button-group size="small">
              <!--              <el-tooltip placement="top" :content="$tu('自动布局')">
                <el-button @click="layout">
                  <iconify icon="tabler:layout-filled" :size="3" />
                </el-button>
              </el-tooltip>-->
              <el-tooltip placement="top" :content="$t('ui.reset')">
                <el-button @click="restart">
                  <iconify icon="solar:eraser-outline" :size="3" />
                </el-button>
              </el-tooltip>
              <el-tooltip placement="top" :content="$t('ui.simulation')">
                <el-button
                  :icon="mockVisible ? VideoPause : VideoPlay"
                  @click="mockVisible = !mockVisible"
                >
                  {{ $t(mockVisible ? 'ui.exitSimulation' : 'ui.startSimulation') }}
                </el-button>
              </el-tooltip>
              <el-tooltip placement="top" :content="$t('ui.validation')">
                <el-button
                  :icon="lintVisible ? VideoPause : VideoPlay"
                  @click="lintVisible = !lintVisible"
                >
                  {{ $t(lintVisible ? 'ui.disableValidation' : 'ui.enableValidation') }}
                </el-button>
              </el-tooltip>
              <el-tooltip placement="top" :content="$t('ui.minimap')">
                <el-button
                  :icon="mapVisible ? VideoPause : VideoPlay"
                  @click="mapVisible = !mapVisible"
                >
                  {{ $t(mapVisible ? 'ui.collapseMinimap' : 'ui.expandMinimap') }}
                </el-button>
              </el-tooltip>
            </el-button-group>
          </el-space>
        </el-header>
        <el-main class="design-inner__main">
          <bpmn-designer @modeler-ready="modelerReady" />
        </el-main>
        <div class="right-panel-arrow" @click="toggleRightArrow">
          <el-icon :size="15">
            <CaretRight v-if="rightArrow && !mockVisible" />
            <CaretLeft v-else />
          </el-icon>
        </div>
      </el-container>
      <el-aside :width="rightArrow && !mockVisible ? '370px' : '0px'" class="design-aside">
        <BpmnPanel
          v-if="modeler"
          :modeler="modeler"
          :size="formSize"
          :label-position="labelPosition"
        ></BpmnPanel>
      </el-aside>
    </el-container>
  </el-container>
</template>

<style scoped lang="scss">
.right-panel-arrow {
  position: absolute;
  top: 50%;
  right: 0;
  z-index: 3;
  transform: translateY(-50%);
  background-color: var(--el-bg-color);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  height: 50px;
  border-radius: 10px 0 0 10px;
  cursor: pointer;
  box-shadow: -7px 0px 7px -5px rgba(0, 0, 0, 0.1);
}

.design-container {
  width: 100%;
  height: 100%;
  overflow: hidden;

  .design-header {
    height: 50px;
    border-bottom: var(--el-border);
    background-color: var(--el-bg-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
  }

  .design-inner__header {
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: var(--el-border);
    // background-color: var(--el-bg-color);
    // box-shadow: var(--el-box-shadow-light);
  }

  .design-inner__main {
    padding: 0;
    height: 100%;
  }

  .design-aside {
    box-shadow: var(--el-box-shadow);
    transition: width 0.3s ease;
    background-color: var(--el-bg-color);
    // z-index: 1;
  }
}

.canvas {
  width: 100%;
  height: 100%;
}
</style>
