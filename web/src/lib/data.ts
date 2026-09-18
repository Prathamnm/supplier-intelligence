// Every number on the site comes from these files, written by
// `python -m pipeline.run` and inlined by Vite at build time.
import summaryJson from '../data/summary.json'
import suppliersJson from '../data/suppliers.json'
import briefsJson from '../data/briefs.json'
import qualityJson from '../data/quality.json'
import type { Brief, QualityReport, Summary, Supplier } from './types'

export const summary = summaryJson as unknown as Summary
export const suppliers = suppliersJson as unknown as Supplier[]
export const briefs = briefsJson as unknown as Brief[]
export const quality = qualityJson as unknown as QualityReport

export const byId = new Map(suppliers.map((s) => [s.supplier_id, s]))
export const briefById = new Map(briefs.map((b) => [b.supplier_id, b]))

export const DIMENSION_LABEL: Record<string, string> = Object.fromEntries(
  summary.dimensions.map((d) => [d.key, d.label]),
)

/** Path to a static brief file, relative so it works under any base path. */
export const briefUrl = (file: string) => `./briefs/${file}`
