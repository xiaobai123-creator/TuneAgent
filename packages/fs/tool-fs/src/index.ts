import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/fs'
import type {} from '@coridis/tools'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'tool-fs'

/** Services required by filesystem tools. */
export const inject = ['tools', 'fs']

/** Tool registration switches. */
export interface Config {
  read?: boolean
}

export const Config: z<Config> = z.object({
  read: z.boolean().default(true),
})

/** Register model-facing filesystem tools. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis tool-fs: tool registration is not implemented')
}

