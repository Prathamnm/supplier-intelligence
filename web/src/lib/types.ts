// Shapes of the JSON written by pipeline/run.py. Kept in one place so a
// pipeline change that breaks the contract fails the type-check.

export type DimensionKey = 'short_delivery' | 'late_delivery' | 'quality_rejection' | 'price_premium'

export interface CategoryRow {
  supplier_id: string
  material_id: string
  orders: number
  spend: number
  short_delivery_pct: number
  late_orders_pct: number
  mean_days_late: number
  quality_rejection_pct: number
  price_premium_pct: number | null
  median_price: number
  benchmark: number | null
  short_loss: number
  reject_loss: number
  return_loss: number
  leakage: number
  score: number
  flags: DimensionKey[]
  low_confidence: boolean
}

export interface YearRow {
  supplier_id: string
  year: number
  orders: number
  spend: number
  short_loss: number
  reject_loss: number
  return_loss: number
}

export interface Supplier {
  supplier_id: string
  supplier_name: string
  score: number
  rank: number
  risk_rank: number
  band: 'act' | 'watch' | 'good'
  drivers: DimensionKey[]
  low_confidence: boolean
  orders: number
  spend: number
  qty_ordered: number
  qty_received: number
  qty_short: number
  qty_rejected: number
  qty_returned: number
  short_delivery_pct: number
  late_orders_pct: number
  mean_days_late: number
  mean_days_late_when_late: number
  max_days_late: number
  receiving_rejection_pct: number
  customer_return_pct: number
  quality_rejection_pct: number
  price_premium_pct: number
  premium_ci_low: number | null
  premium_ci_high: number | null
  premium_q: number
  premium_significant: boolean
  score_short_delivery: number
  score_late_delivery: number
  score_quality_rejection: number
  score_price_premium: number
  short_loss: number
  return_loss: number
  return_loss_recorded: number
  return_loss_inferred: number
  returns_recorded: number
  returns_inferred: number
  reject_loss: number
  handling_loss: number
  premium_loss: number
  premium_net_rs: number
  rubric_core_total: number
  additional_total: number
  total_impact: number
  impact_pct_of_spend: number
  arora_paid_days_late: number | null
}

export type SupplierDetails = Record<string, { categories: CategoryRow[]; years: YearRow[] }>

export interface Score {
  top1: number
  top3: number
  mrr: number
  misallocation: number
  n: number
}

export interface Alternative {
  supplier_id: string
  supplier_name: string
  score: number
  orders: number
  short_pct: number
  days_late: number
  quality_pct: number
  median_price: number
}

export interface Replacement {
  supplier_id: string
  supplier_name: string
  score: number
  rank: number
  total_impact: number
  rubric_core_total: number
  avoidable_total: number
  drivers: DimensionKey[]
  materials: {
    material: string
    orders: number
    spend: number
    leakage: number
    avoidable: number
    alternatives: Alternative[]
  }[]
}

export interface Summary {
  generated_at: string
  runtime_s: number
  stage_times: Record<string, number>
  period: { start: string; end: string; years: number; months: number }
  counts: {
    suppliers: number
    orders: number
    materials: number
    returns: number
    returns_labelled: number
    returns_blank: number
    spend: number
    monthly_spend: number
  }
  totals: {
    short_loss: number
    return_loss: number
    return_loss_inferred: number
    rubric_core_total: number
    reject_loss: number
    handling_loss: number
    premium_loss: number
    total_impact: number
  }
  bottom: {
    suppliers: string[]
    rubric_core_total: number
    total_impact: number
    per_year: number
    excess_over_panel: number
    excess_per_year: number
    excess_rate_of_spend: number
    scaled_to_ps_low: number
    scaled_to_ps_high: number
    share_of_spend: number
    share_of_impact: number
    ps_estimate_low: number
    ps_estimate_high: number
  }
  weights: Record<DimensionKey, number>
  dimensions: { key: DimensionKey; label: string; metric: string; weight: number }[]
  stability: {
    k: number
    stable: boolean
    scenarios: Record<string, { weights: Record<DimensionKey, number>; bottom: string[]; same_as_base: boolean }>
  }
  validation: {
    available: boolean
    flagged: string[]
    our_bottom: string[]
    hits: string[]
    precision: number
    flagged_ranks: Record<string, number>
    n_suppliers: number
    gap_to_next: number | null
  }
  replacements: Replacement[]
  attribution: {
    method: 'model' | 'fallback' | 'none'
    metrics: Score & { cv_folds: number; blend_alpha?: number }
    baselines: Record<string, Score & { label: string }>
    coefficients: Record<string, number>
    feature_labels: Record<string, string>
    calibration: { bin: string; n: number; predicted: number; observed: number }[]
  }
  premium: { significant: string[]; fdr: number }
  index_context: {
    material: string
    index_month: string
    index_price: number
    panel_median: number | null
    panel_vs_index: number
    usable: boolean
    source: string
  }[]
  config: Record<string, number | string>
  quality: { warnings: number; errors: number }
}

export interface ReturnRow {
  return_id: string
  return_date: string
  client_id: string
  material_id: string
  quantity_returned: number
  reason: string
  source: 'recorded' | 'inferred'
  supplier_attributed: string
  confidence: number
  top3: { supplier_id: string; p: number }[]
  model_agrees: boolean | null
}

export interface Brief {
  supplier_id: string
  supplier_name: string
  city: string
  contact: string
  years: number | null
  period: string
  score: number
  rank: number
  n_suppliers: number
  drivers: string[]
  money: Record<string, number | boolean>
  asks: { topic: string; ask: string; evidence: string }[]
  materials: { material: string; orders: number; spend: number; leakage: number; flags: string[] }[]
  evidence: {
    po_id: string
    date: string
    material: string
    ordered: number
    received: number
    rejected: number
    price: number
    billed: number
    received_value: number
    short_loss: number
    days_late: number | null
  }[]
  pushback: string[]
  replace: boolean
  files: { html?: string; pdf?: string; pages?: number }
}

export interface Finding {
  stage: string
  severity: 'info' | 'warning' | 'error'
  title: string
  detail: string
  rows_affected: number | null
  action: string | null
}

export interface QualityReport {
  findings: Finding[]
  counts: Record<string, number>
  n_warnings: number
  n_errors: number
}
