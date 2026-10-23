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
        '无法访问执行服务，请运行 python backend/server.py',
        'Execution service unavailable. Start python backend/server.py.',
      ),
    )
  }
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)
  return data
}
