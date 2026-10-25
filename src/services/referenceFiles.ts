import { translateUi } from '@/languages/uiText'

export async function openReferenceFile(name: string, dataUri: string): Promise<void> {
  let response: Response
  const unavailable = () =>
    translateUi(
      '无法访问本机文件服务。请先运行 python backend/server.py，再重试打开文件。',
      'Local file service unavailable. Start python backend/server.py, then retry opening the file.',
    )
  try {
    response = await fetch('/api/reference-files/open', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, dataUri }),
      signal: AbortSignal.timeout(15000),
    })
  } catch {
    throw new Error(unavailable())
  }
  let result: { ok?: boolean; error?: string }
  try {
    result = await response.json()
  } catch {
    throw new Error(unavailable())
  }
  if (!response.ok || !result.ok) {
    if (response.status >= 500 || response.status === 404) throw new Error(unavailable())
    throw new Error(
      translateUi('本机打开文件失败：', 'Failed to open the local file: ') +
        (result.error || response.status),
    )
  }
}
