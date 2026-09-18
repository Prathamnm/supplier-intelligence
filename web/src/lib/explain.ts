// Plain-language wording for the four checks, shared by every page, so a
// dimension is described the same way wherever it appears.
import { num, pct } from './format'
import type { DimensionKey, Supplier } from './types'
import type { Tone } from '../components/ui'

interface DimensionCopy {
  question: string
  value: (s: Supplier) => number
  /** The supplier's figure, phrased as a fact. */
  phrase: (x: number) => string
  /** The typical supplier's figure, phrased to sit beside it. */
  typical: (x: number) => string
}

export const DIMENSION_COPY: Record<DimensionKey, DimensionCopy> = {
  short_delivery: {
    question: 'Do they deliver the full quantity?',
    value: (s) => s.short_delivery_pct,
    phrase: (x) => `${pct(x, 1)} short`,
    typical: (x) => `${pct(x, 1)} for a typical supplier`,
  },
  late_delivery: {
    question: 'Do they deliver on time?',
    value: (s) => s.mean_days_late,
    phrase: (x) => `${num(x, 1)} days late on average`,
    typical: (x) => `${num(x, 1)} days for a typical supplier`,
  },
  quality_rejection: {
    question: 'Is the material good enough?',
    value: (s) => s.quality_rejection_pct,
    phrase: (x) => `${pct(x, 1)} rejected or returned`,
    typical: (x) => `${pct(x, 1)} for a typical supplier`,
  },
  price_premium: {
    question: 'Do they charge more than others?',
    value: (s) => s.price_premium_pct,
    phrase: (x) => (Math.abs(x) < 0.5 ? 'about the same price as others' : `${pct(Math.abs(x), 1)} ${x > 0 ? 'above' : 'below'} others`),
    typical: (x) => `${x > 0 ? '+' : ''}${pct(x, 1)} for a typical supplier`,
  },
}

export interface VerdictText {
  tone: Tone
  text: string
}

/** One short judgement for a supplier on one check. */
export function verdict(key: DimensionKey, s: Supplier, typical: number, score: number): VerdictText {
  const value = DIMENSION_COPY[key].value(s)

  if (key === 'price_premium') {
    if (s.premium_significant) return { tone: 'crit', text: 'Charges more than others — proven' }
    // Judged on the visible gap, not the score: the score deliberately ignores
    // differences that could be chance, but the words must match the numbers shown.
    if (value - typical < 1) return { tone: 'good', text: value < typical - 1 ? 'Cheaper than others' : 'In line with others' }
    return { tone: 'warn', text: 'A little higher — could be chance, so not claimed' }
  }

  if (value <= typical * 0.9) return { tone: 'good', text: 'Better than typical' }
  if (score >= 90) return { tone: 'good', text: 'In line with typical' }
  const times = typical > 0 ? value / typical : Infinity
  const text = times >= 2 && Number.isFinite(times) ? `${times.toFixed(0)}× worse than typical` : 'Worse than typical'
  return { tone: score < 50 ? 'crit' : 'warn', text }
}

export const median = (xs: number[]) => {
  const a = [...xs].sort((p, q) => p - q)
  const m = Math.floor(a.length / 2)
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}
