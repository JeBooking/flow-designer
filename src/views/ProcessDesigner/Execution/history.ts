import type { ExecutionHistory, ExecutionHistoryPatch } from '@/types/flowableExecution'

export function mergeExecutionHistory(
  previous: ExecutionHistory | undefined,
  patch: ExecutionHistoryPatch,
): ExecutionHistory {
  if (patch.reset || !previous) return { ...patch, review: patch.review ?? { pending: false } }
  if (!patch.changed) return previous
  const variables = new Map(previous.variables.data.map((entry) => [entry.id, entry]))
  const activities = new Map(previous.activities.data.map((entry) => [entry.id, entry]))
  patch.removedVariableIds.forEach((id) => variables.delete(id))
  patch.removedActivityIds.forEach((id) => activities.delete(id))
  patch.variables.data.forEach((entry) => variables.set(entry.id, entry))
  patch.activities.data.forEach((entry) => activities.set(entry.id, entry))
  return {
    ...previous,
    ...patch,
    variables: { data: [...variables.values()] },
    activities: { data: [...activities.values()] },
    review: patch.review ?? previous.review,
  }
}
