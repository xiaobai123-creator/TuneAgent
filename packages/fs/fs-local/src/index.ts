import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/fs'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'fs-local'

/** Provider configuration. */
export interface Config {
  root?: string
}

export const Config: z<Config> = z.object({
  root: z.string(),
})

/** Register the local filesystem provider. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis fs-local: provider registration is not implemented')
}

