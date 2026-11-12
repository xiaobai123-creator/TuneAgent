/** Roles accepted by a model chat transcript. */
export type MessageRole = 'system' | 'user' | 'assistant' | 'tool'

/** One model-visible chat message. */
export interface Message {
  role: MessageRole
  content: string
}

/** One tool invocation requested by the model. */
export interface ToolCall {
  id: string
  name: string
  arguments: unknown
}

/** One tool result returned to the model. */
export interface ToolResult {
  callId: string
  isError: boolean
  content: string
}

/** One user task admitted by the Agent Loop. */
export interface AgentTask {
  prompt: string
  signal: AbortSignal
}

/** Final output of one Agent run. */
export interface AgentResult {
  text: string
}

/** Event vocabulary that the minimal Session log stores. */
export type SessionEvent =
  | { type: 'turn/start'; input: string }
  | { type: 'assistant/message'; text: string }
  | { type: 'tool/call'; call: ToolCall }
  | { type: 'tool/result'; result: ToolResult }
  | { type: 'turn/end'; reason: 'completed' | 'aborted' | 'failed' }

