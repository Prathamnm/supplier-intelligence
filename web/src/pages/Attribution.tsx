import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset, useDetail } from '../lib/dataset'
import { date, frac, inrShort, num } from '../lib/format'
import type { Score } from '../lib/types'
import { Card, Explain, Pill, Section, Stat } from '../components/ui'

type MetricKey = 'value' | 'top3' | 'top1'

// Every measure is shown "higher is better", so the chart reads the same way whichever is picked.
const METRICS: { key: MetricKey; label: string; get: (s: Score) => number; note: string }[] = [
  { key: 'value', label: 'Money on the right supplier', get: (s) => 1 - s.misallocation,
    note: 'Of the value of the hidden returns, how much ended up charged to the right supplier once everything is added up. This is what the rupee totals depend on.' },
  { key: 'top3', label: 'Right supplier in top 3', get: (s) => s.top3,
    note: 'How often the real supplier was among the method’s three most likely suppliers.' },
  { key: 'top1', label: 'Right on first guess', get: (s) => s.top1,
    note: 'How often the real supplier was the method’s single top pick. Hard for any method: nothing on a return says which delivery it came from.' },
]

export default function Attribution() {
  const { summary, byId } = useDataset()
  const returns = useDetail()?.returns
  const a = summary.attribution
  const { counts } = summary
  const [metric, setMetric] = useState<MetricKey>('value')
  const [filter, setFilter] = useState('')

  const methods = [
    { key: 'model', label: 'Our model', ...a.metrics },
    ...Object.entries(a.baselines).map(([key, b]) => ({ key, ...b })),
  ]
  const m = METRICS.find((x) => x.key === metric)!
  const rule = a.baselines.most_recent_batch

  const coefs = Object.entries(a.coefficients).sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]))
  const cmax = Math.max(...coefs.map(([, v]) => Math.abs(v)), 1e-9)

  const inferred = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return (returns ?? [])
      .filter((r) => r.source === 'inferred')
      .filter((r) => !f || `${r.return_id} ${r.material_id} ${r.supplier_attributed} ${r.reason}`.toLowerCase().includes(f))
  }, [returns, filter])

  return (
    <div className="space-y-14">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">Untraced returns</div>
        <h1 className="mt-3 max-w-4xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          {counts.returns_blank} of {counts.returns} customer returns don’t say which supplier they came from. We work out who most likely did.
        </h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          A return note records the material and the date, but not which delivery it came from. So for each return we look at every
          supplier’s track record up to that day — how much of their material we rejected, how often they shorted us, how many returns
          were already traced to them — and estimate how likely each one is to be the source.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {rule && (
          <Stat tone="good" label="Money on the right supplier" value={frac(1 - a.metrics.misallocation)}
            sub={<>When tested on returns where we know the answer. The assignment’s suggested rule: {frac(1 - rule.misallocation)}</>} />
        )}
        {rule && <Stat label="Right supplier in our top 3" value={frac(a.metrics.top3)} sub={<>The suggested rule: {frac(rule.top3)}</>} />}
        <Stat label="Tested on" value={`${a.metrics.n ?? 0} returns`} sub="Each one’s supplier hidden, guessed, then checked" />
        <Stat label="Value of untraced returns" value={inrShort(summary.totals.return_loss_inferred)} sub="Shared out between their likely suppliers" />
      </section>

      <Section eyebrow="Does it work?" title="Tested against simpler approaches"
        lede="We took returns where the supplier is known, hid it, asked each method to guess, and checked the answers."
        aside={
          <div className="flex flex-wrap rounded-lg border border-line bg-surface p-0.5 text-xs">
            {METRICS.map((x) => (
              <button key={x.key} onClick={() => setMetric(x.key)}
                className={`rounded-md px-2.5 py-1.5 ${metric === x.key ? 'bg-surface-2 text-ink' : 'text-ink-3 hover:text-ink'}`}>
                {x.label}
              </button>
            ))}
          </div>
        }>
        <Card className="p-5">
          <div className="space-y-3">
            {methods.map((x) => {
              const v = m.get(x)
              return (
                <div key={x.key} className="grid grid-cols-[1fr_4rem] items-center gap-3 sm:grid-cols-[23rem_1fr_4rem]">
                  <div className="text-sm text-ink-2 sm:truncate" title={x.label}>
                    {x.key === 'model' ? <span className="font-medium text-ink">Our model</span> : x.label}
                  </div>
                  <div className="order-last col-span-2 h-4 rounded-[4px] bg-surface-2 sm:order-none sm:col-span-1">
                    <div className="h-full rounded-[4px]" style={{ width: `${Math.max(v, 0) * 100}%`, background: x.key === 'model' ? 'var(--color-accent)' : 'var(--color-ink-3)' }} />
                  </div>
                  <div className="num text-right text-sm font-medium">{frac(v)}</div>
                </div>
              )
            })}
          </div>
          <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">{m.note}</p>
        </Card>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">
          Why not simply blame whoever delivered that material most recently, as the assignment suggests? Because in this data that’s
          rarely who it was. What does point to the right supplier is their own track record.
        </p>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section eyebrow="How it decides" title="What gives a supplier away"
          lede="The clues the model relies on. A longer bar is a stronger clue: blue makes a supplier more likely to be the source, red less likely.">
          <Card className="p-5">
            <div className="space-y-3">
              {coefs.map(([k, v]) => (
                <div key={k}>
                  <div className="text-sm text-ink">{a.feature_labels[k] ?? k}</div>
                  <div className="relative mt-1 h-2 rounded-full bg-surface-2">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                    <div className="absolute inset-y-0 rounded-full"
                      style={{
                        background: v >= 0 ? 'var(--color-accent)' : 'var(--color-crit)',
                        left: v >= 0 ? '50%' : `${50 - (Math.abs(v) / cmax) * 50}%`,
                        width: `${(Math.abs(v) / cmax) * 50}%`,
                      }} />
                  </div>
                </div>
              ))}
            </div>
          </Card>
          <Explain>
            <p>
              A logistic regression learns these weights from the returns whose supplier is recorded. Every clue is measured using only
              deliveries up to the return’s date, so the model never uses information it couldn’t have had at the time.
            </p>
            <p>
              Its estimates are blended with a simple rule — each supplier’s recent share of that material — in whatever proportion tests
              best ({num(a.metrics.blend_alpha ?? 1, 2)} model here). So it can never do worse than that simple rule, and falls back to it
              on data where there’s nothing to learn.
            </p>
          </Explain>
        </Section>

        <Section eyebrow="Can you trust it?" title="Are the percentages honest?"
          lede="When the model says it’s about 20% sure, it should be right about 20% of the time. Here’s how that held up.">
          <Card className="p-5">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr>
                  <th className="pb-2 text-left font-medium">Model was</th>
                  <th className="pb-2 text-right font-medium">Returns</th>
                  <th className="pb-2 text-right font-medium">Right</th>
                </tr>
              </thead>
              <tbody>
                {a.calibration.map((c) => (
                  <tr key={c.bin} className="border-t border-line">
                    <td className="py-2 text-ink-2">about {frac(c.predicted)} sure</td>
                    <td className="num py-2 text-right text-ink-2">{c.n}</td>
                    <td className="num py-2 text-right font-medium">{frac(c.observed)} of the time</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-xs leading-relaxed text-ink-3">
              Being only 20–30% sure about any single return is expected — several suppliers could have supplied it. That’s why each
              return’s value is shared between the likely suppliers rather than pinned on one, and why negotiation briefs only claim
              returns where the supplier is on record.
            </p>
          </Card>
        </Section>
      </div>

      <Section eyebrow="The result" title={`The ${counts.returns_blank} untraced returns`}
        lede="Each return with its three most likely suppliers, and how likely each one is."
        aside={
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Search return, material, supplier"
            aria-label="Filter untraced returns"
            className="w-64 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm placeholder:text-ink-3 outline-none focus:border-accent" />
        }>
        {!returns ? (
          <Card className="p-6 text-sm text-ink-3">Loading returns…</Card>
        ) : (
          <div className="max-h-[560px] overflow-auto rounded-xl border border-line">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="sticky top-0 bg-surface-2 text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                  <th className="text-left">Return</th><th className="text-left">Date</th><th className="text-left">Material</th>
                  <th className="text-right">Tonnes</th><th className="text-left">Customer’s reason</th><th className="text-left">Most likely suppliers</th>
                </tr>
              </thead>
              <tbody>
                {inferred.map((r) => (
                  <tr key={r.return_id} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                    <td className="num text-ink-2">{r.return_id}</td>
                    <td className="num whitespace-nowrap text-ink-2">{date(r.return_date)}</td>
                    <td className="text-ink-2">{r.material_id}</td>
                    <td className="num text-right text-ink-2">{num(r.quantity_returned, 2)}</td>
                    <td className="text-ink-2">{r.reason}</td>
                    <td>
                      <div className="flex flex-wrap gap-1.5">
                        {r.top3.map((t, i) => (
                          <Link key={t.supplier_id} to={`/supplier/${t.supplier_id}`}>
                            <Pill tone={i === 0 ? 'accent' : 'default'}>
                              {byId.get(t.supplier_id)?.supplier_name ?? t.supplier_id} · {frac(t.p)}
                            </Pill>
                          </Link>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-2 text-xs text-ink-3">{inferred.length} shown.</div>
      </Section>
    </div>
  )
}
