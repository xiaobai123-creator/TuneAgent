import { Service, type Context } from '@deepseek-ai/cordis'

/** One bounded UTF-8 file read request. */
export interface ReadFileRequest {
  path: string
  offset?: number
  limit?: number
}

/** One UTF-8 file read result. */
export interface ReadFileResult {
  path: string
  content: string
  totalLines: number
}

/** Filesystem capability seam for one execution world. */
export abstract class FileSystem extends Service {
  constructor(ctx: Context) {
    super(ctx, 'fs')
  }

  abstract readText(request: ReadFileRequest, signal: AbortSignal): Promise<ReadFileResult>
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    fs: FileSystem
  }
}

