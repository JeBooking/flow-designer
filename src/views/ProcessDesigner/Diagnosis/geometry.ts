import type { Shape, Element, ModdleElement } from 'bpmn-js/lib/model/Types'
import type { DiagnosisKind } from '@/types/diagnosis'
import { getBusinessObject } from 'bpmn-js/lib/util/ModelUtil'
import { getDiagnosisKind } from '@/views/ProcessDesigner/Diagnosis/model'

export function getDiagnosisDetail(element: Element | ModdleElement): string {
  const bo = getBusinessObject(element)
  return String(
    bo.get('flowable:detailText') ??
      (getDiagnosisKind(element) === 'conclusion'
        ? bo.get('flowable:conclusionText')
        : bo.get('flowable:actionText')) ??
      '',
  )
}

export function diagnosisPath(shape: Shape, absolute = false): string {
  const { width: w, height: h } = shape
  const x = absolute ? shape.x : 0
  const y = absolute ? shape.y : 0
  const kind = getDiagnosisKind(shape)
  if (kind === 'jump')
    return `M ${x} ${y + h / 2} a ${w / 2} ${h / 2} 0 1 0 ${w} 0 a ${w / 2} ${h / 2} 0 1 0 ${-w} 0 Z`
  let points: number[][]
  if (kind === 'investigation')
    points = [
      [w / 2, 0],
      [w, h / 2],
      [w / 2, h],
      [0, h / 2],
    ]
  else if (kind === 'investigationAction')
    points = [
      [w * 0.2, 0],
      [w * 0.8, 0],
      [w, h],
      [0, h],
    ]
  else if (kind === 'remediation')
    points = [
      [0, 0],
      [w, 0],
      [w * 0.8, h],
      [w * 0.2, h],
    ]
  else if (kind === 'problemSolved')
    points = [
      [w / 2, 0],
      [w, h],
      [0, h],
    ]
  else if (kind === 'escalation')
    points = Array.from({ length: 10 }, (_, i) => {
      const angle = -Math.PI / 2 + (i * Math.PI) / 5
      const radius = i % 2 ? 0.23 : 0.5
      return [w / 2 + Math.cos(angle) * w * radius, h / 2 + Math.sin(angle) * h * radius]
    })
  else
    points = [
      [0, 0],
      [w, 0],
      [w, h],
      [0, h],
    ]
  return points.map(([px, py], i) => `${i ? 'L' : 'M'} ${x + px} ${y + py}`).join(' ') + ' Z'
}

// 使用形状内接矩形排版，保证多行文字也不会越过斜边。
export function diagnosisTextBox(width: number, height: number, kind?: DiagnosisKind) {
  const ratio =
    kind === 'investigation'
      ? 0.46
      : kind === 'escalation'
        ? 0.33
        : kind === 'problemSolved'
          ? 0.42
          : kind === 'jump'
            ? 0.65
            : kind === 'investigationAction' || kind === 'remediation'
              ? 0.65
              : 0.85
  const boxHeight =
    height *
    (kind === 'escalation'
      ? 0.28
      : kind === 'problemSolved'
        ? 0.36
        : kind === 'investigation'
          ? 0.44
          : 0.65)
  return {
    width: Math.max(8, width * ratio - 8),
    height: Math.max(8, boxHeight),
    centerY: height * (kind === 'problemSolved' ? 0.69 : 0.5),
  }
}

let measuringContext: CanvasRenderingContext2D | null | undefined
function measure(text: string) {
  const context = (measuringContext ??= document.createElement('canvas').getContext('2d'))
  if (!context) return Array.from(text).length * 12
  context.font = '12px Arial, sans-serif'
  return context.measureText(text).width
}

export function labelLines(text: string, width: number): string[] {
  return text.split('\n').flatMap((paragraph) => {
    const lines: string[] = []
    let line = ''
    for (const character of paragraph) {
      if (line && measure(line + character) > width) {
        lines.push(line)
        line = ''
      }
      line += character
    }
    return [...lines, line]
  })
}

export function automaticDiagnosisName(shape: Shape, detail = getDiagnosisDetail(shape)): string {
  const compact = detail.trim().replace(/\s+/g, ' ')
  const box = diagnosisTextBox(shape.width, shape.height, getDiagnosisKind(shape))
  const maxLines = Math.max(1, Math.floor(box.height / 16))
  if (labelLines(compact, box.width).length <= maxLines) return compact
  let result = ''
  for (const character of compact) {
    if (labelLines(result + character + '…', box.width).length > maxLines) break
    result += character
  }
  return result + '…'
}
