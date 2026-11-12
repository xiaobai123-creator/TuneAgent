import { Service, type Context } from '@deepseek-ai/cordis'

/** Immutable identity and cancellation for one tool execution. */
export interface ToolExecutionContext {
  callId: string
  agentId: string
  signal: AbortSignal
}

/** Model-facing tool contract shared by every tool consumer. */
export interface ToolDefinition<Args = unknown, Result = unknown> {
  name: string
  description: string
  parameters: unknown
  execute(args: Args, execution: ToolExecutionContext): Promise<Result>
}

/** Preserve a tool definition's argument and result inference. */
export function defineTool<Args, Result>(
  definition: ToolDefinition<Args, Result>,
): ToolDefinition<Args, Result> {
  return definition
}

/** Tool registry and dispatch seam consumed by the Agent Loop. */
export class ToolsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'tools')
  }

  register<Args, Result>(_definition: ToolDefinition<Args, Result>): () => void {
    throw new Error('coridis tools: registration is not implemented')
  }

  async execute<Args, Result>(
    _name: string,
    _args: Args,
    _execution: ToolExecutionContext,
  ): Promise<Result> {
    throw new Error('coridis tools: execution is not implemented')
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    tools: ToolsService
  }
}

