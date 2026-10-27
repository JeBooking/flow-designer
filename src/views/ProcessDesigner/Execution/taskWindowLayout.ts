export interface TaskRect {
  x: number
  y: number
  width: number
  height: number
}

export interface TaskPoint {
  x: number
  y: number
}

export function clampWindow(rect: TaskRect, width: number, height: number): TaskRect {
  return {
    ...rect,
    x: Math.max(8, Math.min(rect.x, width - rect.width - 8)),
    y: Math.max(60, Math.min(rect.y, height - rect.height - 8)),
  }
}

function overlap(a: TaskRect, b: TaskRect) {
  return (
    Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) *
    Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))
  )
}

export function placeTaskWindow(
  source: TaskRect,
  size: Pick<TaskRect, 'width' | 'height'>,
  occupied: TaskRect[],
  nodes: TaskRect[],
  viewport: { width: number; height: number },
): TaskRect {
  const gap = 28
  const candidates: TaskRect[] = []
  for (const offset of [0, 80, -80, 160, -160]) {
    candidates.push(
      { ...size, x: source.x + source.width + gap, y: source.y + offset },
      { ...size, x: source.x - size.width - gap, y: source.y + offset },
      { ...size, x: source.x + offset, y: source.y + source.height + gap },
      { ...size, x: source.x + offset, y: source.y - size.height - gap },
    )
  }
  for (let y = 60; y < viewport.height; y += 72) {
    for (let x = 8; x < viewport.width; x += 100) candidates.push({ ...size, x, y })
  }
  const score = (rect: TaskRect) =>
    occupied.reduce((total, other) => total + overlap(rect, other) * 20, 0) +
    nodes.reduce((total, node) => total + overlap(rect, node) * 3, 0) +
    Math.hypot(rect.x - source.x, rect.y - source.y)
  return candidates
    .map((rect) => clampWindow(rect, viewport.width, viewport.height))
    .reduce((best, rect) => (score(rect) < score(best) ? rect : best))
}

export function rectEdge(rect: TaskRect, toward: TaskPoint): TaskPoint {
  const center = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
  const dx = toward.x - center.x
  const dy = toward.y - center.y
  const ratio = Math.min(
    rect.width / 2 / Math.max(Math.abs(dx), 0.001),
    rect.height / 2 / Math.max(Math.abs(dy), 0.001),
  )
  return { x: center.x + dx * ratio, y: center.y + dy * ratio }
}
