// Client for the analysis API (api/main.py). In development Vite proxies
// /api to the local server; a deployed build points VITE_UPLOAD_API_URL at it.
import type { Brief, QualityReport, Summary, Supplier } from './types'

const BASE = (import.meta.env.VITE_UPLOAD_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export const apiUrl = (path: string) => `${BASE}/api${path}`

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// A free-tier host can take up to a minute to wake; beyond that, give up
// and say so rather than leaving the page waiting forever.
const CONNECT_TIMEOUT_MS = 90_000

async function request<T>(path: string, init?: RequestInit, timeoutMs = CONNECT_TIMEOUT_MS): Promise<T> {
  let res: Response
  try {
    res = await fetch(apiUrl(path), { ...init, signal: init?.signal ?? AbortSignal.timeout(timeoutMs) })
  } catch (e) {
    const timedOut = e instanceof DOMException && e.name === 'TimeoutError'
    throw new ApiError(0, timedOut
      ? 'The analysis server did not respond in time.'
      : 'The analysis server could not be reached.')
  }
  if (!res.ok) throw new ApiError(res.status, await detail(res))
  return res.json() as Promise<T>
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status}).`
}

export interface Schema {
  files: Record<string, string[]>
  /** File types the analysis can do without. */
  optional?: string[]
  max_file_mb: number
  max_files: number
}

export interface AnalysisMeta {
  id: string
  source: 'upload'
  created: string
  completed?: string
  runtime_s?: number
  status: 'running' | 'done'
  files: { name: string; bytes: number; detected_as: string | null }[]
  headline?: { suppliers: number; orders: number; bottom: string[]; warnings: number }
}

export interface AnalysisData {
  meta: AnalysisMeta
  summary: Summary
  suppliers: Supplier[]
  briefs: Brief[]
  quality: QualityReport
}

export const getHealth = () => request<{ status: string; ready?: boolean }>('/health')

/**
 * Nudge the API awake as soon as the site opens, so it is usually ready by
 * the time someone reaches the Upload page. Fire-and-forget: failures don't matter.
 */
export function wakeApi(): void {
  getHealth().catch(() => undefined)
}
export const getSchema = () => request<Schema>('/schema')

/**
 * Upload files and run the analysis. Uses XHR rather than fetch so the
 * page can show real upload progress; the analysis itself then takes a
 * few seconds server-side.
 */
export function createAnalysis(files: File[], onUpload: (fraction: number) => void): Promise<AnalysisMeta> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl('/analyses'))
    // Room for a sleeping server to wake (~1 min) plus the analysis itself.
    xhr.timeout = 180_000
    xhr.ontimeout = () => reject(new ApiError(0, 'The analysis server took too long to respond. Please try again.'))
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => e.lengthComputable && onUpload(e.loaded / e.total)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as AnalysisMeta)
      else reject(new ApiError(xhr.status, xhr.response?.detail ?? `Upload failed (${xhr.status}).`))
    }
    xhr.onerror = () => reject(new ApiError(0, 'The analysis server could not be reached.'))
    xhr.send(form)
  })
}

const data = <T,>(id: string, name: string) => request<T>(`/analyses/${id}/data/${name}`)

/** Everything the overview pages need, fetched in parallel. */
export async function loadAnalysis(id: string): Promise<AnalysisData> {
  const [meta, summary, suppliers, briefs, quality] = await Promise.all([
    request<AnalysisMeta>(`/analyses/${id}`),
    data<Summary>(id, 'summary.json'),
    data<Supplier[]>(id, 'suppliers.json'),
    data<Brief[]>(id, 'briefs.json'),
    data<QualityReport>(id, 'quality.json'),
  ])
  return { meta, summary, suppliers, briefs, quality }
}

/**
 * Download an analysis's printable pages (briefs and the approach document)
 * into the browser as blob: URLs, keyed by file name. The hosted API forgets
 * uploads when it restarts; a copy held here keeps "Open to print" working
 * for as long as the tab is open. Pages that fail to load are simply left out.
 */
export async function cachePages(id: string, files: string[]): Promise<Map<string, string>> {
  const pages = new Map<string, string>()
  await Promise.all(
    files.map(async (file) => {
      const path = file === APPROACH_PAGE ? `/analyses/${id}/approach` : `/analyses/${id}/briefs/${encodeURIComponent(file)}`
      try {
        const res = await fetch(apiUrl(path), { signal: AbortSignal.timeout(30_000) })
        if (!res.ok) return
        const html = await res.text()
        pages.set(file, URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' })))
      } catch {
        /* keep the server link for this one */
      }
    }),
  )
  return pages
}

export const APPROACH_PAGE = 'approach.html'

export const loadAnalysisDetail = (id: string) =>
  Promise.all([data(id, 'supplier_details.json'), data(id, 'returns.json')])
