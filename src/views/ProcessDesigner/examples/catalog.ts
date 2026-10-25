import type { DiagnosticExample } from '@/types/diagnosis'
import dependencies from '@/views/ProcessDesigner/examples/parallel-dependencies.bpmn?raw'
import temperature from '@/views/ProcessDesigner/examples/diagnostic-demo.bpmn?raw'
import voltage from '@/views/ProcessDesigner/examples/voltage-diagnosis.bpmn?raw'
import communication from '@/views/ProcessDesigner/examples/communication-retry.bpmn?raw'
import sensors from '@/views/ProcessDesigner/examples/sensor-comparison.bpmn?raw'
import pressure from '@/views/ProcessDesigner/examples/pressure-recovery.bpmn?raw'
import humanDecision from '@/views/ProcessDesigner/examples/human-decision.bpmn?raw'

const legacyExamples: DiagnosticExample[] = [
  {
    id: 'human-decision',
    title: '人工判断与回退',
    titleEn: 'Human decisions and rechecks',
    description:
      'Python 绘图后等待确认，人工填写的结论无需 Python，处置后由人选择结果。每个等待节点均可回退。',
    descriptionEn:
      'Confirm Python charts, review a manual conclusion, and choose the recovery outcome. Every human wait offers a return to earlier nodes.',
    xml: humanDecision,
    scenarios: ['recover', 'severe', 'normal'],
  },
  {
    id: 'temperature',
    title: '温度综合诊断',
    titleEn: 'Temperature diagnosis',
    description: '覆盖全部八类节点，包含自检、恢复、深度分析、上升和跳转。',
    descriptionEn:
      'All eight node types: self-test, recovery, deep analysis, escalation and handoff.',
    xml: temperature,
    scenarios: ['recover', 'normal', 'action', 'escalate', 'severe', 'jump'],
  },
  {
    id: 'voltage',
    title: '电源电压诊断',
    titleEn: 'Power supply diagnosis',
    description: '先绘制电压曲线，形成结论，再验证恢复措施是否有效。',
    descriptionEn: 'Plot supply voltage, form a conclusion, then verify recovery.',
    xml: voltage,
    scenarios: ['recover', 'normal', 'severe'],
  },
  {
    id: 'communication',
    title: '通信重试诊断',
    titleEn: 'Communication retries',
    description: '异步检查连接，执行复位后重新排查；最多三次，失败后上升。',
    descriptionEn:
      'Check asynchronously and retry after reset, with at most three attempts before escalation.',
    xml: communication,
    scenarios: ['recover', 'normal', 'offline'],
  },
  {
    id: 'sensors',
    title: '双传感器对比',
    titleEn: 'Dual sensor comparison',
    description: '根据差异选择 A 或 B 分支，汇合时仅读取实际执行的支路结果。',
    descriptionEn:
      'Select the A or B branch from measured differences, then merge only the executed branch.',
    xml: sensors,
    scenarios: ['sensor-a', 'sensor-b', 'normal', 'severe'],
  },
  {
    id: 'pressure',
    title: '压力处置与交接',
    titleEn: 'Pressure recovery and handoff',
    description: '依次泄压和复位，再分析压力趋势，决定解决、上升或交接。',
    descriptionEn:
      'Vent and reset in sequence, then analyze the pressure trend and resolve, escalate or hand off.',
    xml: pressure,
    scenarios: ['stable', 'leak', 'unknown'],
  },
]

export const diagnosticExamples: DiagnosticExample[] = [
  {
    id: 'parallel-dependencies',
    title: '并行排查与依赖',
    titleEn: 'Parallel investigations and dependencies',
    description:
      '是与否各有两条并行连线；A 路径依赖供电检查，B 路径独立执行。多项处置可到达问题解决。自动匹配参数，支持无参数、无返回值的动作。',
    descriptionEn:
      'Yes and No each have two parallel connections. Path A depends on a power check; B runs independently. Multiple actions reach Problem Solved. Parameters are automatic; void actions are supported.',
    xml: dependencies,
    scenarios: ['normal', 'unavailable'],
  },
  ...legacyExamples.map((example) => ({
    ...example,
    title: example.title + '（旧版）',
    titleEn: example.titleEn + ' (legacy)',
    description:
      '旧版互斥连线示例：运行前须将排查出口改为是/否，并将动作上的条件判断移到排查节点。' +
      example.description,
    descriptionEn:
      'Legacy exclusive routing: assign Yes/No investigation branches and move action decisions into investigations before running. ' +
      example.descriptionEn,
  })),
]
