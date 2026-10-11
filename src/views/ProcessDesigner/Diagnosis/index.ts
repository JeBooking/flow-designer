import DiagnosisRules from '@/views/ProcessDesigner/Diagnosis/DiagnosisRules'
import DiagnosisRenderer from '@/views/ProcessDesigner/Diagnosis/DiagnosisRenderer'

export default {
  __init__: ['diagnosisRules', 'diagnosisRenderer'],
  diagnosisRules: ['type', DiagnosisRules],
  diagnosisRenderer: ['type', DiagnosisRenderer],
}
