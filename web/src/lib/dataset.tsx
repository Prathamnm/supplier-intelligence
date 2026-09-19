// The dataset every page renders: the bundled assignment results, or an
// analysis the user uploaded. Both have exactly the same shape -- the API
// serves the same JSON files the build bundles -- so pages never branch
// on where their data came from.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { APPROACH_PAGE, apiUrl, cachePages, loadAnalysis, loadAnalysisDetail, type AnalysisMeta } from './api'
import * as bundled from './data'
import type { Brief, QualityReport, ReturnRow, Summary, Supplier, SupplierDetails } from './types'

export interface Detail {
  details: SupplierDetails
  returns: ReturnRow[]
}

export interface Dataset {
  key: string
  source: 'bundled' | 'upload'
  label: string
  meta?: AnalysisMeta
  summary: Summary
  suppliers: Supplier[]
  briefs: Brief[]
  quality: QualityReport
  byId: Map<string, Supplier>
  briefById: Map<string, Brief>
  dimensionLabel: Record<string, string>
  briefUrl: (file: string) => string
  approachUrl: string
  loadDetail: () => Promise<Detail>
}

function build(parts: Omit<Dataset, 'byId' | 'briefById' | 'dimensionLabel' | 'loadDetail'> & {
  fetchDetail: () => Promise<Detail>
}): Dataset {
  let detail: Promise<Detail> | null = null
  const { fetchDetail, ...rest } = parts
  return {
    ...rest,
    byId: new Map(parts.suppliers.map((s) => [s.supplier_id, s])),
    briefById: new Map(parts.briefs.map((b) => [b.supplier_id, b])),
    dimensionLabel: Object.fromEntries(parts.summary.dimensions.map((d) => [d.key, d.label])),
    // Fetched once per dataset, on first use.
    loadDetail: () => (detail ??= fetchDetail()),
  }
}

const BUNDLED = build({
  key: 'assignment',
  source: 'bundled',
  label: 'Assignment data',
  summary: bundled.summary,
  suppliers: bundled.suppliers,
  briefs: bundled.briefs,
  quality: bundled.quality,
  briefUrl: (file) => `./briefs/${file}`,
  approachUrl: './approach.pdf',
  fetchDetail: () => import('./detail').then((m) => ({ details: m.details, returns: m.returns })),
})

const STORAGE_KEY = 'si.analysis'

interface DatasetState {
  dataset: Dataset
  /** Switch every page to an analysis held by the API. */
  activate: (id: string) => Promise<void>
  /** Back to the bundled assignment results. */
  reset: () => void
  notice: string | null
}

const Ctx = createContext<DatasetState | null>(null)

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [dataset, setDataset] = useState<Dataset>(BUNDLED)
  const [notice, setNotice] = useState<string | null>(null)
  // blob: URLs of the current upload's printable pages, released when replaced.
  const pages = useRef<Map<string, string>>(new Map())
  const releasePages = useCallback(() => {
    for (const url of pages.current.values()) URL.revokeObjectURL(url)
    pages.current = new Map()
  }, [])

  const activate = useCallback(async (id: string) => {
    const a = await loadAnalysis(id)
    // The server prints each PDF the first time it is asked for, so every brief
    // offers one; the printable pages are copied into the tab straight away.
    const briefs = a.briefs.map((b) => ({
      ...b,
      files: { ...b.files, pdf: b.files.pdf ?? b.files.html?.replace(/\.html$/, '.pdf') },
    }))
    const htmlFiles = briefs.flatMap((b) => (b.files.html ? [b.files.html] : []))
    const cached = await cachePages(id, [...htmlFiles, APPROACH_PAGE])
    releasePages()
    pages.current = cached
    const ds = build({
      key: id,
      source: a.meta.source,
      label: `Your upload (${a.meta.files.length} files)`,
      meta: a.meta,
      summary: a.summary,
      suppliers: a.suppliers,
      briefs,
      quality: a.quality,
      briefUrl: (file) => cached.get(file) ?? apiUrl(`/analyses/${id}/briefs/${encodeURIComponent(file)}`),
      approachUrl: apiUrl(`/analyses/${id}/approach.pdf`),
      fetchDetail: () =>
        loadAnalysisDetail(id).then(([details, returns]) => ({
          details: details as SupplierDetails,
          returns: returns as ReturnRow[],
        })),
    })
    // Fetch the per-supplier detail now too, while the server certainly has it.
    ds.loadDetail().catch(() => undefined)
    setDataset(ds)
    setNotice(null)
    try {
      sessionStorage.setItem(STORAGE_KEY, id)
    } catch {
      /* storage unavailable: the analysis still shows, it just won't survive a reload */
    }
  }, [releasePages])

  const reset = useCallback(() => {
    releasePages()
    setDataset(BUNDLED)
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      /* ignore */
    }
  }, [releasePages])

  // Open an analysis from a shared link (#/overview?analysis=<id>), or restore the
  // one from before a page reload -- if the server still has it.
  useEffect(() => {
    let id = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('analysis')
    if (!id) {
      try {
        id = sessionStorage.getItem(STORAGE_KEY)
      } catch {
        /* storage unavailable */
      }
    }
    if (!id) return
    activate(id).catch(() => {
      reset()
      setNotice('Your uploaded analysis has expired on the server, so the assignment data is shown instead.')
    })
  }, [activate, reset])

  const value = useMemo(() => ({ dataset, activate, reset, notice }), [dataset, activate, reset, notice])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDatasetState(): DatasetState {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useDataset must be used inside <DatasetProvider>')
  return ctx
}

export const useDataset = () => useDatasetState().dataset

/** Per-supplier detail and return rows, loaded on demand. Null while loading. */
export function useDetail(): Detail | null {
  const ds = useDataset()
  const [loaded, setLoaded] = useState<{ key: string; detail: Detail } | null>(null)
  useEffect(() => {
    let live = true
    ds.loadDetail().then((detail) => live && setLoaded({ key: ds.key, detail }))
    return () => {
      live = false
    }
  }, [ds])
  return loaded?.key === ds.key ? loaded.detail : null
}
