// Client for the analysis API (api/main.py). In development Vite proxies
// /api to the local server; a deployed build points VITE_API_URL at it.
import type { Brief, QualityReport, Summary, Supplier } from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export const apiUrl = (path: string) => `${BASE}/api${path}`

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(apiUrl(path), init)
  } catch {
    throw new ApiError(0, 'The analysis server could not be reached.')
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
  max_file_mb: number
  max_files: number
}

export interface Sample {
  name: string
  title: string
  purpose: string
  suppliers: number
  orders: number
}

export interface AnalysisMeta {
  id: string
  source: 'upload' | 'sample'
  sample?: string
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

export const getHealth = () => request<{ status: string }>('/health')
export const getSchema = () => request<Schema>('/schema')
export const getSamples = () => request<Sample[]>('/samples')
export const analyseSample = (name: string) =>
  request<AnalysisMeta>(`/samples/${encodeURIComponent(name)}`, { method: 'POST' })

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

export const loadAnalysisDetail = (id: string) =>
  Promise.all([data(id, 'supplier_details.json'), data(id, 'returns.json')])
