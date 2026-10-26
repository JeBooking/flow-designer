export interface PythonParameter {
  name: string
  kind:
    | 'POSITIONAL_ONLY'
    | 'POSITIONAL_OR_KEYWORD'
    | 'KEYWORD_ONLY'
    | 'VAR_POSITIONAL'
    | 'VAR_KEYWORD'
  required: boolean
  default?: string
  annotation?: string
}
export interface PythonInterface {
  name: string
  signature: string
  description: string
  parameters: PythonParameter[]
}
export interface PythonProject {
  id: string
  name: string
  path: string
  module: string
  factory?: string
  python: string
  moduleFile: string
  interfaces: PythonInterface[]
  initParameters?: PythonParameter[]
}
export interface PythonProjectRegistration {
  name: string
  path: string
  module: string
  factory?: string
  python: string
}
export interface PythonCallResult {
  ok: boolean
  sessionId?: string
  result?: unknown
  representation?: 'json' | 'repr'
  stdout?: string
  stderr?: string
  error?: string
  traceback?: string
}
