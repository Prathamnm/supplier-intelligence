import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Supplier } from '../lib/types'
import { inrShort, num, pct } from '../lib/format'
import { BandBadge, scoreText } from './ui'

type Col = {
  key: keyof Supplier
  label: string
  title?: string
  render: (s: Supplier) => string
  align?: 'right'
}

const COLS: Col[] = [
  { key: 'rank', label: 'Rank', render: (s) => String(s.rank), align: 'right' },
  { key: 'score', label: 'Score', render: (s) => s.score.toFixed(0), align: 'right' },
  { key: 'short_delivery_pct', label: 'Short', title: 'Share of the ordered quantity that never arrived', render: (s) => pct(s.short_delivery_pct, 2), align: 'right' },
  { key: 'mean_days_late', label: 'Days late', title: 'Average delay per order, in days', render: (s) => num(s.mean_days_late, 1), align: 'right' },
  { key: 'quality_rejection_pct', label: 'Rejected / returned', title: 'Share of what arrived that we rejected or customers sent back', render: (s) => pct(s.quality_rejection_pct, 2), align: 'right' },
  { key: 'price_premium_pct', label: 'Price vs others', title: 'How much more (or less) they charge than other suppliers for the same material', render: (s) => `${s.price_premium_pct > 0 ? '+' : ''}${pct(s.price_premium_pct)}`, align: 'right' },
  { key: 'rubric_core_total', label: 'Short + returns', title: 'Money lost to short deliveries and customer returns', render: (s) => inrShort(s.rubric_core_total), align: 'right' },
  { key: 'total_impact', label: 'Total lost', render: (s) => inrShort(s.total_impact), align: 'right' },
]

export function LeagueTable({ rows }: { rows: Supplier[] }) {
  const nav = useNavigate()
  const [sort, setSort] = useState<{ key: keyof Supplier; dir: 1 | -1 }>({ key: 'rank', dir: -1 })
  const [q, setQ] = useState('')

  const data = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const filtered = needle
      ? rows.filter((s) => `${s.supplier_id} ${s.supplier_name}`.toLowerCase().includes(needle))
      : rows
    return [...filtered].sort((a, b) => {
      const x = a[sort.key] as number, y = b[sort.key] as number
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir
    })
  }, [rows, sort, q])

  const toggle = (key: keyof Supplier) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: -1 }))

  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search supplier or ID"
          aria-label="Filter suppliers"
          className="w-full max-w-xs rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-3 outline-none focus:border-accent"
        />
        <span className="text-xs text-ink-3">{data.length} of {rows.length}</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
            <tr>
              <th className="px-3 py-2.5 text-left font-medium">Supplier</th>
              {COLS.map((c) => (
                <th
                  key={c.key}
                  title={c.title}
                  aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}
                  className={`px-3 py-2.5 font-medium ${c.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  <button onClick={() => toggle(c.key)} className="inline-flex items-center gap-1 uppercase hover:text-ink">
                    {c.label}
                    <span className={sort.key === c.key ? 'text-accent' : 'opacity-0'}>{sort.dir === 1 ? '↑' : '↓'}</span>
                  </button>
                </th>
              ))}
              <th className="px-3 py-2.5 text-left font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr
                key={s.supplier_id}
                onClick={() => nav(`/supplier/${s.supplier_id}`)}
                className="cursor-pointer border-t border-line transition-colors hover:bg-surface-2/70"
              >
                <td className="px-3 py-2">
                  {/* The link makes each row reachable by keyboard; the row click is a mouse convenience. */}
                  <Link to={`/supplier/${s.supplier_id}`} onClick={(e) => e.stopPropagation()}
                        className="font-medium text-ink outline-none hover:text-accent focus-visible:underline">
                    {s.supplier_name}
                  </Link>
                  <div className="num text-xs text-ink-3">{s.supplier_id} · {s.orders} orders</div>
                </td>
                {COLS.map((c) => (
                  <td key={c.key} className={`num px-3 py-2 ${c.align === 'right' ? 'text-right' : ''} ${c.key === 'score' ? `font-semibold ${scoreText(s.score)}` : 'text-ink-2'}`}>
                    {c.render(s)}
                  </td>
                ))}
                <td className="px-3 py-2"><BandBadge band={s.band} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
