export interface PythonInterface {
  name: string
  signature: string
  description: string
}
export interface PythonProject {
  id: string
  name: string
  path: string
  module: string
  python: string
  moduleFile: string
  interfaces: PythonInterface[]
}
export interface PythonProjectRegistration {
  name: string
  path: string
  module: string
  python: string
}
export interface PythonCallResult {
  ok: boolean
  result?: unknown
  representation?: 'json' | 'repr'
  stdout?: string
  stderr?: string
  error?: string
  traceback?: string
}
