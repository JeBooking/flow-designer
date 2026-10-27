import type { DiagnosisReviewState } from '@/types/diagnosis'

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
  startTime?: string
  endTime?: string
  durationInMillis?: number
}
export interface ExecutionFailure {
  id: string
  activityId?: string
  exceptionMessage?: string
  traceback?: string
  [key: string]: unknown
}
export interface ExecutionHistory {
  process: { endTime?: string; [key: string]: unknown }
  activities: { data: ExecutionActivity[] }
  variables: { data: { variable?: { name?: string; value?: unknown } }[] }
  review: DiagnosisReviewState
  pendingReviews?: DiagnosisReviewState[]
  failures?: ExecutionFailure[]
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
