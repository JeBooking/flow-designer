import DiagnosisRules from '@/views/ProcessDesigner/Diagnosis/DiagnosisRules'
import DiagnosisRenderer from '@/views/ProcessDesigner/Diagnosis/DiagnosisRenderer'
import DiagnosisBehavior from '@/views/ProcessDesigner/Diagnosis/DiagnosisBehavior'
import DiagnosisBranchBehavior from '@/views/ProcessDesigner/Diagnosis/DiagnosisBranchBehavior'

export default {
  __init__: ['diagnosisRules', 'diagnosisRenderer', 'diagnosisBehavior', 'diagnosisBranchBehavior'],
  diagnosisBranchBehavior: ['type', DiagnosisBranchBehavior],
  diagnosisBehavior: ['type', DiagnosisBehavior],
  diagnosisRules: ['type', DiagnosisRules],
  diagnosisRenderer: ['type', DiagnosisRenderer],
}
