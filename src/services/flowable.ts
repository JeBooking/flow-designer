export async function flowableRequest<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/flowable/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const raw = await response.text()
  let data: T & { error?: string }
  try {
    data = JSON.parse(raw)
  } catch {
    throw new Error(
      translateUi(
        '执行服务暂不可用，请检查服务状态后重试',
        'Execution service is unavailable. Check its status and retry.',
      ),
    )
  }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
  return data
}
