import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Supplier } from '../lib/types'
import { inrShort } from '../lib/format'
import { Tip } from './ui'

/**
 * The hero: every supplier on the panel as one bar, ordered best to worst
 * by scorecard, height = rupees lost. The underperformers stand out at the
 * right without a caption. The chart is also the navigation.
 */
export function PanelStrip({ rows }: { rows: Supplier[] }) {
  const nav = useNavigate()
  const sorted = [...rows].sort((a, b) => b.score - a.score)
  const max = Math.max(...rows.map((r) => r.total_impact))
  const [hover, setHover] = useState<{ s: Supplier; x: number; y: number } | null>(null)

  return (
    <div className="relative">
      <div
        className="flex h-40 items-end gap-[3px] sm:h-48"
        role="list"
        aria-label={`All ${rows.length} suppliers, best scorecard on the left; bar height is rupees lost`}
        onMouseLeave={() => setHover(null)}
      >
        {sorted.map((s, i) => {
          const tone = s.band === 'act' ? 'bg-crit' : s.band === 'watch' ? 'bg-warn' : 'bg-ink-3/55'
          return (
            <button
              key={s.supplier_id}
              role="listitem"
              aria-label={`${s.supplier_name}, score ${s.score.toFixed(0)}, ${inrShort(s.total_impact)} quantified`}
              onClick={() => nav(`/supplier/${s.supplier_id}`)}
              onMouseEnter={(e) => {
                const r = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect()
                const b = e.currentTarget.getBoundingClientRect()
                setHover({ s, x: b.left - r.left + b.width / 2, y: b.top - r.top })
              }}
              onFocus={(e) => {
                const r = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect()
                const b = e.currentTarget.getBoundingClientRect()
                setHover({ s, x: b.left - r.left + b.width / 2, y: b.top - r.top })
              }}
              onBlur={() => setHover(null)}
              className="group relative h-full min-w-0 flex-1 cursor-pointer outline-none"
            >
              <span
                className={`absolute inset-x-0 bottom-0 origin-bottom rounded-t-[4px] ${tone} animate-rise transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:ring-2 group-focus-visible:ring-accent ${hover && hover.s !== s ? 'opacity-45' : 'opacity-90'}`}
                style={{ height: `${Math.max((s.total_impact / max) * 100, 2)}%`, animationDelay: `${i * 14}ms` }}
              />
            </button>
          )
        })}
      </div>
      <div className="mt-2 flex justify-between border-t border-line pt-2 text-[11px] uppercase tracking-[.1em] text-ink-3">
        <span>← Best suppliers</span>
        <span className="hidden sm:inline">Taller bar = more money lost</span>
        <span>Worst suppliers →</span>
      </div>
      {hover && (
        <Tip x={hover.x} y={hover.y}>
          <div className="font-medium text-ink">{hover.s.supplier_name} <span className="text-ink-3">{hover.s.supplier_id}</span></div>
          <div className="mt-1 flex justify-between gap-4 text-ink-2"><span>Score</span><span className="num text-ink">{hover.s.score.toFixed(0)}/100</span></div>
          <div className="flex justify-between gap-4 text-ink-2"><span>Rank</span><span className="num text-ink">{hover.s.rank} of {rows.length}</span></div>
          <div className="flex justify-between gap-4 text-ink-2"><span>Quantified</span><span className="num text-ink">{inrShort(hover.s.total_impact)}</span></div>
        </Tip>
      )}
    </div>
  )
}
