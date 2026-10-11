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
