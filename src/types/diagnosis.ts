export type DiagnosisKind = 'investigation' | 'conclusion' | 'remediation' | 'escalation'

export interface InvestigationData {
  observation: string
  acquisition: string
  referenceImage: string
  assessment: string
}
