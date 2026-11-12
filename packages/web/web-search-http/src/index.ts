import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@coridis/web'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'web-search-http'

/** Services required by the search provider. */
export const inject = ['web']

/** Search provider configuration. */
export interface Config {
  endpoint?: string
}

export const Config: z<Config> = z.object({
  endpoint: z.string(),
})

/** Register the HTTP search provider on `ctx.web`. */
export function apply(_ctx: Context, _config: Config): void {
  throw new Error('coridis web-search-http: provider registration is not implemented')
}

