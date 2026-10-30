import { defineStore } from 'pinia'

export const useExecutionStore = defineStore(
  'execution-monitor',
  () => {
    const runId = ref('')
    const recentRunIds = ref<string[]>([])
    function remember(id: string) {
      runId.value = id
      recentRunIds.value = [id, ...recentRunIds.value.filter((entry) => entry !== id)].slice(0, 10)
    }
    function forget() {
      runId.value = ''
    }
    return { runId, recentRunIds, remember, forget }
  },
  { persist: { pick: ['runId', 'recentRunIds'] } },
)
