export type DiagnosisKind =
  | 'investigation'
  | 'investigationAction'
  | 'conclusion'
  | 'remediation'
  | 'deepDiagnosis'
  | 'jump'
  | 'problemSolved'
  | 'escalation'

export interface InvestigationData {
  observation: string
  acquisition: string
  referenceImage: string
  referenceImageName?: string
  assessment: string
}

export interface DiagnosticExample {
  id: string
  title: string
  titleEn: string
  description: string
  descriptionEn: string
  xml: string
  scenarios: string[]
}

export interface DiagnosisReviewState {
  pending: boolean
  evidence?: unknown
  inputs?: unknown
  kind?: DiagnosisKind
  canRecheck?: boolean
  taskId?: string
  nodeId?: string
  mode?: 'decision' | 'escalation' | 'success' | 'action'
  actionMode?: 'manual' | 'confirm'
  lastActionResult?: 'ok' | 'not_ok'
  name?: string
  options?: { id: string; name: string; paths?: { id: string; name: string; target: string }[] }[]
  instructions?: Partial<
    InvestigationData & { conclusionText: string; actionText: string; detailText: string }
  >
  candidates?: { id: string; name: string }[]
}
export type DiagnosisBranch = 'yes' | 'no'
export type DiagnosisActionMode = 'automatic' | 'manual' | 'confirm'
export type DiagnosisExecutionMode = 'parallel' | 'serial'
export type DiagnosisNameMode = 'auto' | 'manual'

export interface DiagnosisFailure {
  nodeId: string
  reason: string
  branch?: DiagnosisBranch
  path?: string[]
  time?: string
}
