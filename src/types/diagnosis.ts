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
  taskId?: string
  nodeId?: string
  mode?: 'decision' | 'escalation'
  name?: string
  options?: { id: string; name: string }[]
  instructions?: Partial<InvestigationData & { conclusionText: string; actionText: string }>
  candidates?: { id: string; name: string }[]
}
export type DiagnosisBranch = 'yes' | 'no'
