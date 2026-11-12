import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/web'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'web-fetch-http'

/** Services required by the fetch provider. */
export const inject = ['web']

/** Fetch provider configuration. */
export interface Config {
  timeoutMs?: number
  maxBytes?: number
}

export const Config: z<Config> = z.object({
  timeoutMs: z.number().default(30000),
  maxBytes: z.number().default(1000000),
})

/** Register the HTTP fetch provider on `ctx.web`. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis web-fetch-http: provider registration is not implemented')
}

