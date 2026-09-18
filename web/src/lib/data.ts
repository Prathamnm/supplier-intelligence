// The bundled assignment results, written by `python -m pipeline.run` and
// inlined by Vite at build time. Pages read them through useDataset().
import summaryJson from '../data/summary.json'
import suppliersJson from '../data/suppliers.json'
import briefsJson from '../data/briefs.json'
import qualityJson from '../data/quality.json'
import type { Brief, QualityReport, Summary, Supplier } from './types'

export const summary = summaryJson as unknown as Summary
export const suppliers = suppliersJson as unknown as Supplier[]
export const briefs = briefsJson as unknown as Brief[]
export const quality = qualityJson as unknown as QualityReport
