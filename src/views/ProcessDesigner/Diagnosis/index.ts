import DiagnosisRules from '@/views/ProcessDesigner/Diagnosis/DiagnosisRules'
import DiagnosisRenderer from '@/views/ProcessDesigner/Diagnosis/DiagnosisRenderer'
import DiagnosisBehavior from '@/views/ProcessDesigner/Diagnosis/DiagnosisBehavior'

export default {
  __init__: ['diagnosisRules', 'diagnosisRenderer', 'diagnosisBehavior'],
  diagnosisBehavior: ['type', DiagnosisBehavior],
  diagnosisRules: ['type', DiagnosisRules],
  diagnosisRenderer: ['type', DiagnosisRenderer],
}
