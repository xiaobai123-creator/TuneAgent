import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type { AgentResult, AgentTask } from '@coridis/contracts'
import type {} from '@coridis/llm'
import type {} from '@coridis/session'
import type {} from '@coridis/tools'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'agent-loop'

/** Capabilities that must exist before the loop can start. */
export const inject = ['llm', 'tools', 'sessions']

/** Minimal loop bounds. */
export interface Config {
  maxSteps?: number
}

export const Config: z<Config> = z.object({
  maxSteps: z.number().default(20),
})

/** Run one task to completion. */
export async function run(_ctx: Context, _task: AgentTask): Promise<AgentResult> {
  throw new Error('coridis agent-loop: run is not implemented')
}

/** Install the loop plugin. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis agent-loop: plugin installation is not implemented')
}

