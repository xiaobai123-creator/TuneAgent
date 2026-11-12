import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/tools'
import type {} from '@coridis/web'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'tool-web'

/** Services required by web tools. */
export const inject = ['tools', 'web']

/** Tool registration switches. */
export interface Config {
  search?: boolean
  fetch?: boolean
}

export const Config: z<Config> = z.object({
  search: z.boolean().default(true),
  fetch: z.boolean().default(true),
})

/** Register model-facing web tools. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis tool-web: tool registration is not implemented')
}

