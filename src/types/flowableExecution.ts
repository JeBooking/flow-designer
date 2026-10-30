import type { DiagnosisActionMode, DiagnosisReviewState } from '@/types/diagnosis'

export type ExecutionNodeStatus = 'idle' | 'active' | 'completed' | 'waiting' | 'failed'
export type ExecutionStatus = 'loading' | 'running' | 'waiting' | 'paused' | 'failed' | 'ended'
export interface ExecutionNode {
  id: string
  name: string
}
export interface ExecutionActivity {
  id?: string
  activityId: string
  activityName?: string
  activityType: string
  startTime?: string | null
  endTime?: string | null
  durationInMillis?: number | null
}
export interface ExecutionFailure {
  id: string
  activityId?: string
  exceptionMessage?: string
  traceback?: string
  [key: string]: unknown
}
export interface DiagnosticFailure {
  id?: string
  nodeId?: string
  node?: string
  code?: string
  source?: string
  reason?: string
  branch?: string
  path?: string[]
  time?: string
  [key: string]: unknown
}
export interface ExecutionHistory {
  process: { endTime?: string | null; [key: string]: unknown }
  activities: { data: ExecutionActivity[] }
  variables: { data: { id?: string; variable?: { name?: string; value?: unknown } }[] }
  review: DiagnosisReviewState
  pendingReviews?: DiagnosisReviewState[]
  failures?: ExecutionFailure[]
  nodes?: ExecutionNode[]
  cursor?: string
}

export interface ExecutionHistoryPatch extends Omit<ExecutionHistory, 'review'> {
  review?: DiagnosisReviewState
  reset: boolean
  changed: boolean
  removedVariableIds: string[]
  removedActivityIds: string[]
}
export interface ExecutionNodeView extends ExecutionNode {
  status: ExecutionNodeStatus
  occurrences: ExecutionActivity[]
  hasResult: boolean
  result: unknown
  traces?: ExecutionTrace[]
  reviews?: ExecutionReview[]
}

export type ExecutionInstructions = NonNullable<DiagnosisReviewState['instructions']>

export interface ExecutionTrace {
  version: 1
  id: string
  nodeId: string
  jobId?: string
  startedAt: string
  endedAt: string
  status: 'completed' | 'waiting' | 'failed'
  inputs?: unknown
  factoryInputs?: unknown
  evidence?: unknown
  result?: unknown
  route?: unknown
  instructions?: ExecutionInstructions
  judgmentInstructions?: string
  error?: unknown
  traceback?: string
  call?: { module?: string; factory?: string; function?: string }
}

export interface ExecutionReview {
  mode?: DiagnosisReviewState['mode']
  actionMode?: DiagnosisActionMode
  actionResult?: 'ok' | 'not_ok'
  nodeId?: string
  taskId?: string
  from?: string
  action?: string
  time?: string
  next?: unknown
  selectedFlowIds?: string[]
  reason?: unknown
  target?: unknown
  previousResult?: unknown
  clearedResults?: unknown
  inputChanges?: unknown
  inputs?: unknown
  evidence?: unknown
  instructions?: ExecutionInstructions
}
