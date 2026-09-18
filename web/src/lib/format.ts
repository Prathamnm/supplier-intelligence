// Indian number formatting throughout: ₹12,34,567, not ₹1,234,567.
const full = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const plain = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export const inr = (x: number | null | undefined) => (x == null || !isFinite(x) ? '—' : full.format(x))

/** Compact rupees for tiles and axes: ₹8.42 L, ₹1.24 Cr. */
export function inrShort(x: number | null | undefined, digits = 2): string {
  if (x == null || !isFinite(x)) return '—'
  const a = Math.abs(x)
  if (a >= 1e7) return `₹${(x / 1e7).toFixed(digits)} Cr`
  if (a >= 1e5) return `₹${(x / 1e5).toFixed(digits)} L`
  if (a >= 1e3) return `₹${(x / 1e3).toFixed(1)} K`
  return `₹${x.toFixed(0)}`
}

export const num = (x: number, digits = 0) =>
  new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(x)

export const int = (x: number) => plain.format(x)

export const pct = (x: number | null | undefined, digits = 1) =>
  x == null || !isFinite(x) ? '—' : `${x.toFixed(digits)}%`

/** 0-1 fraction as a percentage. */
export const frac = (x: number | null | undefined, digits = 0) =>
  x == null || !isFinite(x) ? '—' : `${(x * 100).toFixed(digits)}%`

export const date = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

export const monthYear = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
