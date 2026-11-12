import { Service, type Context } from '@deepseek-ai/cordis'
import type { Message, ToolCall } from '@coridis/contracts'

/** One model request assembled by the Agent Loop. */
export interface LlmRequest {
  model: string
  messages: readonly Message[]
  tools: readonly LlmToolSchema[]
  signal: AbortSignal
}

/** Model-facing declaration of one callable tool. */
export interface LlmToolSchema {
  name: string
  description: string
  parameters: unknown
}

/** One streamed model output fragment. */
export type LlmChunk =
  | { type: 'text-delta'; text: string }
  | { type: 'tool-call'; call: ToolCall }
  | { type: 'finish'; reason: 'stop' | 'tool-calls' | 'length' | 'aborted' }

/** A swappable model provider registered on `ctx.llm`. */
export interface LlmProvider {
  readonly id: string
  stream(request: LlmRequest): AsyncIterable<LlmChunk>
}

/** Model capability seam. Providers register here; the Agent Loop consumes it. */
export class LlmService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'llm')
  }

  registerProvider(_provider: LlmProvider): () => void {
    throw new Error('coridis llm: provider registration is not implemented')
  }

  stream(_request: LlmRequest): AsyncIterable<LlmChunk> {
    throw new Error('coridis llm: streaming is not implemented')
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    llm: LlmService
  }
}

