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
  failures?: ExecutionFailure[]
}
export interface ExecutionNodeView extends ExecutionNode {
  status: ExecutionNodeStatus
  occurrences: ExecutionActivity[]
  hasResult: boolean
  result: unknown
}
