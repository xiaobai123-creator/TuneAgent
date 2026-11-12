#!/usr/bin/env node
import type { Context } from '@deepseek-ai/cordis'

/** Cordis plugin name used by loader diagnostics. */
export const name = 'coridis-cli'

/** Start the minimal profile. */
export async function main(_ctx: Context): Promise<void> {
  throw new Error('coridis cli: bootstrap is not implemented')
}

