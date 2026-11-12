import { Service, type Context } from '@deepseek-ai/cordis'
import type { SessionEvent } from '@coridis/contracts'

/** Durable Session log seam. */
export class SessionService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'sessions')
  }

  async append(_event: SessionEvent): Promise<number> {
    throw new Error('coridis session: append is not implemented')
  }

  async *events(_signal: AbortSignal): AsyncIterable<SessionEvent> {
    throw new Error('coridis session: replay is not implemented')
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    sessions: SessionService
  }
}

