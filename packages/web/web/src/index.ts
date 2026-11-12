import { Service, type Context } from '@deepseek-ai/cordis'

/** One web search request. */
export interface WebSearchRequest {
  query: string
  maxResults?: number
}

/** One search source. */
export interface WebSearchSource {
  title: string
  url: string
  snippet?: string
}

/** Search results returned to the tool consumer. */
export interface WebSearchResult {
  sources: readonly WebSearchSource[]
}

/** One web fetch request. */
export interface WebFetchRequest {
  url: string
  maxChars?: number
}

/** Retrieved page content. */
export interface WebFetchResult {
  url: string
  status: number
  contentType?: string
  content: string
}

/** Search provider seam. */
export interface WebSearchProvider {
  readonly id: string
  search(request: WebSearchRequest, signal: AbortSignal): Promise<WebSearchResult>
}

/** Fetch provider seam. */
export interface WebFetchProvider {
  readonly id: string
  fetch(request: WebFetchRequest, signal: AbortSignal): Promise<WebFetchResult>
}

/** Web capability seam consumed by web tools. */
export class WebService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'web')
  }

  registerSearchProvider(_provider: WebSearchProvider): () => void {
    throw new Error('coridis web: search provider registration is not implemented')
  }

  registerFetchProvider(_provider: WebFetchProvider): () => void {
    throw new Error('coridis web: fetch provider registration is not implemented')
  }

  async search(_request: WebSearchRequest, _signal: AbortSignal): Promise<WebSearchResult> {
    throw new Error('coridis web: search is not implemented')
  }

  async fetch(_request: WebFetchRequest, _signal: AbortSignal): Promise<WebFetchResult> {
    throw new Error('coridis web: fetch is not implemented')
  }
}

declare module '@deepseek-ai/cordis' {
  interface Context {
    web: WebService
  }
}

