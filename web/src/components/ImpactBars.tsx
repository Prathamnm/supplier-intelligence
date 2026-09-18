import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Supplier } from '../lib/types'
import { inr, inrShort } from '../lib/format'
import { Tip } from './ui'

// Fixed slot order -- colour follows the loss type, never its rank.
export const LOSS_SERIES = [
  { key: 'short_loss', label: 'Short delivery', color: 'var(--color-s1)', core: true },
  { key: 'return_loss_recorded', label: 'Returns — recorded', color: 'var(--color-s2)', core: true },
  { key: 'return_loss_inferred', label: 'Returns — inferred', color: 'var(--color-s3)', core: true },
  { key: 'reject_loss', label: 'Rejected at inspection', color: 'var(--color-s4)', core: false },
  { key: 'handling_loss', label: 'Return handling', color: 'var(--color-s5)', core: false },
] as const

type Key = (typeof LOSS_SERIES)[number]['key']

export function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2">
      {LOSS_SERIES.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: s.color }} aria-hidden />
          {s.label}
          {!s.core && <span className="text-ink-3">(additional)</span>}
        </span>
      ))}
    </div>
  )
}

/** Horizontal stacked bars: rupees lost per supplier, by loss type. */
export function ImpactBars({ rows, limit = 12 }: { rows: Supplier[]; limit?: number }) {
  const top = [...rows].sort((a, b) => b.total_impact - a.total_impact).slice(0, limit)
  const max = Math.max(...top.map((r) => r.total_impact))
  const [hover, setHover] = useState<{ s: Supplier; k: Key; x: number; y: number } | null>(null)

  return (
    <div className="relative" onMouseLeave={() => setHover(null)}>
      <div className="space-y-2">
        {top.map((s) => (
          <div key={s.supplier_id} className="grid grid-cols-[7.5rem_1fr_5.5rem] items-center gap-3 sm:grid-cols-[11rem_1fr_6.5rem]">
            <Link to={`/supplier/${s.supplier_id}`} className="truncate text-sm text-ink-2 hover:text-ink">
              <span className="num text-ink-3">{s.supplier_id}</span> {s.supplier_name}
            </Link>
            <div className="flex h-5 gap-[2px]">
              {LOSS_SERIES.map((ser) => {
                const v = s[ser.key]
                if (v <= 0) return null
                return (
                  <div
                    key={ser.key}
                    className="h-full cursor-default first:rounded-l-[4px] last:rounded-r-[4px] transition-opacity"
                    style={{
                      width: `${(v / max) * 100}%`,
                      background: ser.color,
                      opacity: hover && (hover.s !== s || hover.k !== ser.key) ? 0.4 : 1,
                    }}
                    onMouseMove={(e) => {
                      const r = (e.currentTarget.closest('.relative') as HTMLElement).getBoundingClientRect()
                      setHover({ s, k: ser.key, x: e.clientX - r.left, y: e.clientY - r.top })
                    }}
                  />
                )
              })}
            </div>
            <div className="num text-right text-sm font-medium text-ink">{inrShort(s.total_impact)}</div>
          </div>
        ))}
      </div>
      {hover && (
        <Tip x={hover.x} y={hover.y}>
          <div className="font-medium text-ink">{hover.s.supplier_name}</div>
          {LOSS_SERIES.map((ser) => (
            <div key={ser.key} className={`mt-0.5 flex items-center justify-between gap-4 ${ser.key === hover.k ? 'text-ink' : 'text-ink-3'}`}>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-[2px]" style={{ background: ser.color }} />
                {ser.label}
              </span>
              <span className="num">{inr(hover.s[ser.key])}</span>
            </div>
          ))}
        </Tip>
      )}
    </div>
  )
}
