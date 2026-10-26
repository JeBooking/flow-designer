import type {
  PythonProject,
  PythonProjectRegistration,
  PythonCallResult,
} from '@/types/pythonProject'

async function request<T>(path: string, body?: unknown, allowCallFailure = false): Promise<T> {
  const response = await fetch(`/api/projects${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const text = await response.text()
  let data: T & PythonCallResult
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(
      translateUi(
        'Python 服务没有返回有效响应，请先运行 python backend/server.py。',
        'Invalid backend response. Start python backend/server.py first.',
      ),
    )
  }
  if (!response.ok && !(allowCallFailure && data.sessionId && data.ok === false)) {
    throw new Error(
      [data.error || `HTTP ${response.status}`, data.traceback, data.stdout, data.stderr]
        .filter(Boolean)
        .join('\n'),
    )
  }
  return data
}
export const listPythonProjects = () => request<{ projects: PythonProject[] }>('')
export const registerPythonProject = (project: PythonProjectRegistration) =>
  request<{ project: PythonProject }>('', project)
export const refreshPythonProject = (id: string) =>
  request<{ project: PythonProject }>(`/${encodeURIComponent(id)}/refresh`, {})
export const removePythonProject = (id: string) =>
  request<{ ok: boolean }>(`/${encodeURIComponent(id)}/remove`, {})
export const callPythonInterface = (
  id: string,
  name: string,
  args: unknown[],
  kwargs: Record<string, unknown>,
  sessionId?: string,
  inputs?: Record<string, unknown>,
) =>
  request<PythonCallResult>(
    `/${encodeURIComponent(id)}/call`,
    { function: name, args, kwargs, sessionId, inputs },
    true,
  )
export const closePythonSession = (id: string, sessionId: string) =>
  request<{ ok: boolean }>(`/${encodeURIComponent(id)}/sessions/close`, { sessionId })
