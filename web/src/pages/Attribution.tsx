import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { byId, summary } from '../lib/data'
import { returns } from '../lib/detail'
import { date, frac, inrShort, num } from '../lib/format'
import { Card, Pill, Section, Stat } from '../components/ui'

type Metric = 'misallocation' | 'top3' | 'top1'

const METRICS: { key: Metric; label: string; better: 'low' | 'high'; note: string }[] = [
  { key: 'misallocation', label: 'Value misallocated', better: 'low', note: 'Share of returns assigned to the wrong supplier once summed per supplier — what the rupee totals depend on.' },
  { key: 'top3', label: 'Right supplier in top 3', better: 'high', note: 'Share of held-out returns where the recorded supplier is among the three most likely.' },
  { key: 'top1', label: 'Right supplier ranked first', better: 'high', note: 'Hard for any method here: nothing on a return identifies its batch.' },
]

export default function Attribution() {
  const a = summary.attribution
  const { counts } = summary
  const [metric, setMetric] = useState<Metric>('misallocation')
  const [filter, setFilter] = useState('')

  const methods = [
    { key: 'model', label: 'Our model', ...a.metrics },
    ...Object.entries(a.baselines).map(([key, b]) => ({ key, ...b })),
  ]
  const m = METRICS.find((x) => x.key === metric)!
  const max = Math.max(...methods.map((x) => x[metric]), 0.01)

  const coefs = Object.entries(a.coefficients).sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]))
  const cmax = Math.max(...coefs.map(([, v]) => Math.abs(v)))

  const inferred = useMemo(() => {
    const f = filter.trim().toLowerCase()
    return returns
      .filter((r) => r.source === 'inferred')
      .filter((r) => !f || `${r.return_id} ${r.material_id} ${r.supplier_attributed} ${r.reason}`.toLowerCase().includes(f))
  }, [filter])

  return (
    <div className="space-y-14">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">The missing-attribution challenge</div>
        <h1 className="mt-3 max-w-4xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          {counts.returns_blank} of {counts.returns} customer returns name no supplier. We learn who they most likely came from — and prove it on the {counts.returns_labelled} that do.
        </h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          A return has a material and a date but no purchase order or batch number, so it cannot be joined to a delivery.
          The model scores every supplier who had delivered before the return date, using only their history up to that date, and
          outputs a probability for each. Rupee totals split a return’s value by those probabilities; the negotiation brief claims only recorded returns.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat tone="good" label="Value misallocated" value={frac(a.metrics.misallocation, 1)}
          sub={<>vs {frac(a.baselines.most_recent_batch.misallocation)} for the problem statement’s most-recent-batch rule</>} />
        <Stat label="Right supplier in top 3" value={frac(a.metrics.top3)} sub={<>vs {frac(a.baselines.most_recent_batch.top3)} for the rule</>} />
        <Stat label="Evaluated on" value={`${a.metrics.n} returns`} sub={<>{a.metrics.cv_folds}-fold cross-validation, grouped by return</>} />
        <Stat label="Inferred value" value={inrShort(summary.totals.return_loss_inferred)} sub={<>{counts.returns_blank} untraced returns, split by probability</>} />
      </section>

      <Section eyebrow="Validation" title="Model vs baselines, on returns whose supplier is known"
        lede="Each method sees a held-out return with its supplier hidden, predicts, and is scored against the recorded answer."
        aside={
          <div className="flex rounded-lg border border-line bg-surface p-0.5 text-xs">
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
            {methods.map((x) => (
              <div key={x.key} className="grid grid-cols-[1fr_4rem] items-center gap-3 sm:grid-cols-[18rem_1fr_4rem]">
                <div className="text-sm text-ink-2 sm:truncate" title={x.label}>
                  {x.key === 'model' ? <span className="font-medium text-ink">Our model</span> : x.label}
                </div>
                <div className="order-last col-span-2 h-4 rounded-[4px] bg-surface-2 sm:order-none sm:col-span-1">
                  <div className="h-full rounded-[4px]" style={{ width: `${(x[metric] / max) * 100}%`, background: x.key === 'model' ? 'var(--color-accent)' : 'var(--color-ink-3)' }} />
                </div>
                <div className="num text-right text-sm font-medium">{frac(x[metric], 1)}</div>
              </div>
            ))}
          </div>
          <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">{m.note} {m.better === 'low' ? 'Lower is better.' : 'Higher is better.'}</p>
        </Card>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-ink-2">
          Why the rule in the problem statement does poorly here: on the returns that <em>are</em> labelled, the recorded supplier is
          rarely the one whose batch of that material arrived most recently. What does predict the source is the supplier’s own record —
          whose deliveries failed our inspection, arrived short, or were returned before.
        </p>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section eyebrow="What the model learned" title="Feature weights"
          lede="Standardised logistic-regression coefficients, fitted on the labelled returns. Positive means “more likely the source”.">
          <Card className="p-5">
            <div className="space-y-3">
              {coefs.map(([k, v]) => (
                <div key={k}>
                  <div className="flex justify-between text-sm">
                    <span className="text-ink">{a.feature_labels[k] ?? k}</span>
                    <span className="num text-ink-2">{v > 0 ? '+' : ''}{v.toFixed(2)}</span>
                  </div>
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
        </Section>

        <Section eyebrow="Calibration" title="Does “20% likely” mean right 20% of the time?"
          lede="Held-out returns grouped by the model’s confidence in its top pick, against how often that pick was right.">
          <Card className="p-5">
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr><th className="pb-2 text-left font-medium">Confidence</th><th className="pb-2 text-right font-medium">Returns</th><th className="pb-2 text-right font-medium">Predicted</th><th className="pb-2 text-right font-medium">Observed</th></tr>
              </thead>
              <tbody>
                {a.calibration.map((c) => (
                  <tr key={c.bin} className="border-t border-line">
                    <td className="py-2 text-ink-2">{c.bin}</td>
                    <td className="num py-2 text-right text-ink-2">{c.n}</td>
                    <td className="num py-2 text-right">{frac(c.predicted, 1)}</td>
                    <td className="num py-2 text-right">{frac(c.observed, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-xs leading-relaxed text-ink-3">
              Confidence on a single return is modest by design: several suppliers could have supplied any given return. That uncertainty is why
              rupee totals use the full probability split, and why inferred returns are shown in briefs but never demanded as a credit.
            </p>
          </Card>
        </Section>
      </div>

      <Section eyebrow="Output" title={`The ${counts.returns_blank} inferred returns`}
        lede="Each untraced return with its three most likely suppliers."
        aside={
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by ID, material, supplier"
            aria-label="Filter inferred returns"
            className="w-64 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm placeholder:text-ink-3 outline-none focus:border-accent" />
        }>
        <div className="max-h-[560px] overflow-auto rounded-xl border border-line">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="sticky top-0 bg-surface-2 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Return</th><th className="text-left">Date</th><th className="text-left">Material</th>
                <th className="text-right">MT</th><th className="text-left">Reason</th><th className="text-left">Most likely suppliers</th>
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
                            {t.supplier_id} {frac(t.p)}
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
        <div className="mt-2 text-xs text-ink-3">
          {inferred.length} shown. Supplier names: {summary.bottom.suppliers.map((id) => `${id} ${byId.get(id)?.supplier_name}`).join(' · ')}.
        </div>
      </Section>
    </div>
  )
}
