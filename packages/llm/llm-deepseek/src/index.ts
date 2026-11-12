import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/llm'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'llm-deepseek'

/** Services required by the DeepSeek provider. */
export const inject = ['llm']

/** DeepSeek provider configuration. */
export interface Config {
  baseUrl?: string
  apiKeyEnv?: string
  model?: string
}

export const Config: z<Config> = z.object({
  baseUrl: z.string().default('https://api.deepseek.com'),
  apiKeyEnv: z.string().default('DEEPSEEK_API_KEY'),
  model: z.string().default('deepseek-chat'),
})

/** Register the DeepSeek provider on `ctx.llm`. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis llm-deepseek: provider registration is not implemented')
}

