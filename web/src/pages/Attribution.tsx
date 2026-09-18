import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDataset, useDetail } from '../lib/dataset'
import { date, frac, inrShort, num } from '../lib/format'
import type { ReturnRow } from '../lib/types'
import { Card, Explain, Pill, Section, Stat } from '../components/ui'

type MetricKey = 'misallocation' | 'top3' | 'top1'

const METRICS: { key: MetricKey; label: string; better: 'low' | 'high'; note: string }[] = [
  { key: 'misallocation', label: 'Value misallocated', better: 'low',
    note: 'Share of the hidden returns’ value that ends up charged to the wrong supplier, once everything is added up per supplier. This is what the rupee totals depend on.' },
  { key: 'top3', label: 'Right supplier in top 3', better: 'high',
    note: 'How often the real supplier was among the method’s three most likely suppliers.' },
  { key: 'top1', label: 'Right supplier ranked first', better: 'high',
    note: 'How often the real supplier was the method’s single top pick. Hard for any method: nothing on a return says which delivery it came from.' },
]

export default function Attribution() {
  const { summary, byId } = useDataset()
  const returns = useDetail()?.returns
  const a = summary.attribution
  const { counts } = summary
  const [metric, setMetric] = useState<MetricKey>('misallocation')
  const [filter, setFilter] = useState('')

  const methods = [
    { key: 'model', label: 'Our model', ...a.metrics },
    ...Object.entries(a.baselines).map(([key, b]) => ({ key, ...b })),
  ]
  const m = METRICS.find((x) => x.key === metric)!
  const max = Math.max(...methods.map((x) => x[metric]), 0.01)
  const rule = a.baselines.most_recent_batch

  const coefs = Object.entries(a.coefficients).sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]))
  const cmax = Math.max(...coefs.map(([, v]) => Math.abs(v)), 1e-9)

  // A real untraced return to walk through: the clearest-cut one, so the example reads easily.
  const example = useMemo(() => {
    const untraced = (returns ?? []).filter((r) => r.source === 'inferred' && r.top3.length > 0)
    return untraced.reduce<ReturnRow | undefined>((best, r) => (!best || r.top3[0].p > best.top3[0].p ? r : best), undefined)
  }, [returns])

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
          A return note records what came back and when, but not which supplier sent it. Without a supplier, its cost can’t be
          charged to anyone. So for each one we estimate who most likely supplied it, from every supplier’s track record up to that
          day, and share its value out accordingly.
        </p>

        {example && (
          <Card className="mt-6 max-w-3xl p-5">
            <div className="text-xs font-medium uppercase tracking-[.1em] text-ink-3">Example</div>
            <p className="mt-2 text-sm leading-relaxed text-ink">
              <b>{num(example.quantity_returned, 2)} MT of {example.material_id}</b> came back on {date(example.return_date)}{' '}
              (“{example.reason}”). No supplier was written down. Our estimate of who supplied it:
            </p>
            <div className="mt-3 space-y-1.5">
              {example.top3.map((t) => (
                <div key={t.supplier_id} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm sm:grid-cols-[14rem_1fr_3rem]">
                  <Link to={`/supplier/${t.supplier_id}`} className="truncate text-ink-2 hover:text-accent">
                    {byId.get(t.supplier_id)?.supplier_name ?? t.supplier_id}
                  </Link>
                  <div className="h-2 rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-accent" style={{ width: `${t.p * 100}%` }} />
                  </div>
                  <span className="num text-right text-ink-2">{frac(t.p)}</span>
                </div>
              ))}
              <div className="text-xs text-ink-3">…and smaller chances for the other suppliers.</div>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-2">
              The return’s value is shared out in these proportions, so no single supplier is blamed for it outright — and briefs never
              ask a supplier to pay for an untraced return.
            </p>
          </Card>
        )}
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {rule && (
          <Stat tone="good" label="Value misallocated" value={frac(a.metrics.misallocation, 1)}
            sub={<>Charged to the wrong supplier when tested (lower is better). The assignment’s suggested rule: {frac(rule.misallocation)}</>} />
        )}
        {rule && <Stat label="Right supplier in our top 3" value={frac(a.metrics.top3)} sub={<>The suggested rule: {frac(rule.top3)}</>} />}
        <Stat label="Tested on" value={`${a.metrics.n ?? 0} returns`} sub="Each one’s supplier hidden, guessed, then checked" />
        <Stat label="Value of untraced returns" value={inrShort(summary.totals.return_loss_inferred)} sub="Shared out between their likely suppliers" />
      </section>

      <Section eyebrow="Does it work?" title="Tested against simpler approaches"
        lede={`To check the estimates, we took the ${a.metrics.n ?? 0} returns where the supplier IS recorded, covered up the answer, let each method guess, then compared.`}
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
              const v = x[metric]
              return (
                <div key={x.key} className="grid grid-cols-[1fr_4rem] items-center gap-3 sm:grid-cols-[minmax(0,24rem)_1fr_4rem]">
                  <div className="text-sm leading-snug text-ink-2">
                    {x.key === 'model' ? <span className="font-medium text-ink">Our model</span> : x.label}
                  </div>
                  <div className="order-last col-span-2 h-4 rounded-[4px] bg-surface-2 sm:order-none sm:col-span-1">
                    <div className="h-full rounded-[4px]" style={{ width: `${(v / max) * 100}%`, background: x.key === 'model' ? 'var(--color-accent)' : 'var(--color-ink-3)' }} />
                  </div>
                  <div className="num text-right text-sm font-medium">{frac(v, 1)}</div>
                </div>
              )
            })}
          </div>
          <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">{m.note} {m.better === 'low' ? 'Lower is better.' : 'Higher is better.'}</p>
        </Card>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">
          Why not simply blame whoever delivered that material most recently, as the assignment suggests? Because in this data that’s
          rarely who it was. What does point to the right supplier is their own track record.
        </p>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-3">
          One assumption: the returns with a supplier written down are typical of those without. If clerks recorded the supplier more
          often for some suppliers than others, the estimates would lean towards those suppliers — which is why only recorded returns
          are ever claimed from a supplier.
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
