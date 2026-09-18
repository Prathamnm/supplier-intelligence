import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDataset, useDetail } from '../lib/dataset'
import { date, inr, inrShort, num, pct } from '../lib/format'
import type { DimensionKey, Supplier } from '../lib/types'
import { BandBadge, Card, Meter, Pill, scoreText, Section, Stat, toneFor } from '../components/ui'

const DIM_VALUE: Record<DimensionKey, { get: (s: Supplier) => number; fmt: (x: number) => string; note: string }> = {
  short_delivery: { get: (s) => s.short_delivery_pct, fmt: (x) => pct(x, 2), note: 'of ordered quantity not delivered' },
  late_delivery: { get: (s) => s.mean_days_late, fmt: (x) => `${num(x, 1)} days`, note: 'late per order, on average' },
  quality_rejection: { get: (s) => s.quality_rejection_pct, fmt: (x) => pct(x, 2), note: 'rejected at inspection or returned by customers' },
  price_premium: { get: (s) => s.price_premium_pct, fmt: (x) => `${x > 0 ? '+' : ''}${pct(x, 1)}`, note: 'vs other suppliers, same material and quarter' },
}

const median = (xs: number[]) => {
  const a = [...xs].sort((p, q) => p - q)
  const m = Math.floor(a.length / 2)
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}

export default function SupplierPage() {
  const { id = '' } = useParams()
  const { summary, suppliers, byId, briefById, dimensionLabel: DIMENSION_LABEL, briefUrl } = useDataset()
  const detail = useDetail()
  const returns = detail?.returns
  const s = byId.get(id)
  const brief = briefById.get(id)
  const replacement = summary.replacements.find((r) => r.supplier_id === id)
  const myReturns = useMemo(() => (returns ?? []).filter((r) => r.supplier_attributed === id), [returns, id])

  if (!s) {
    return (
      <div className="py-24 text-center">
        <div className="text-lg font-semibold">No supplier “{id}”</div>
        <Link to="/" className="mt-2 inline-block text-accent">Back to overview</Link>
      </div>
    )
  }

  const panelMedian = (k: DimensionKey) => median(suppliers.map(DIM_VALUE[k].get))
  const { categories, years } = detail?.details[id] ?? { categories: [], years: [] }
  const maxYear = Math.max(...years.map((y) => y.short_loss + y.return_loss + y.reject_loss), 1)

  return (
    <div className="space-y-12">
      {/* header */}
      <section className="animate-fade">
        <Link to="/" className="text-xs text-ink-3 hover:text-ink">← All suppliers</Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight">{s.supplier_name}</h1>
              <BandBadge band={s.band} />
              {replacement && <Pill tone="crit">Replacement candidate</Pill>}
            </div>
            <div className="num mt-1 text-sm text-ink-3">
              {s.supplier_id} · {s.orders} orders · {inrShort(s.spend)} spend · rank {s.rank} of {suppliers.length}
            </div>
          </div>
          {brief && (
            <div className="flex gap-2">
              {brief.files.pdf && (
                <a href={briefUrl(brief.files.pdf)} target="_blank" rel="noreferrer"
                   className="rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-bg hover:bg-ink-2">
                  Negotiation brief · PDF
                </a>
              )}
              {brief.files.html && (
                <a href={briefUrl(brief.files.html)} target="_blank" rel="noreferrer"
                   className="rounded-lg border border-line px-3.5 py-2 text-sm text-ink-2 hover:text-ink">
                  Print view
                </a>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Score" value={<span className={scoreText(s.score)}>{s.score.toFixed(0)}<span className="text-base text-ink-3">/100</span></span>} sub={`Rank ${s.rank} of ${suppliers.length}`} />
        <Stat label="Short delivery + returns" value={inrShort(s.rubric_core_total)} sub="The problem statement’s formula" />
        <Stat label="Total quantified" value={inrShort(s.total_impact)} sub={`${pct(s.impact_pct_of_spend, 2)} of spend`} />
        <Stat label="Returns attributed" value={num(s.returns_recorded + s.returns_inferred, 1)} sub={`${num(s.returns_recorded, 0)} recorded · ${num(s.returns_inferred, 1)} inferred (expected)`} />
      </section>

      {/* dimensions */}
      <Section eyebrow="Scorecard" title="Four dimensions against the panel"
        lede="Each dimension scores 100 when a supplier is at or better than the typical supplier, falling to 0 at six standard deviations worse (never counting differences too small to matter). The raw rate is shown against the panel median.">
        <div className="grid gap-3 md:grid-cols-2">
          {summary.dimensions.map((d) => {
            const score = s[`score_${d.key}` as keyof Supplier] as number
            const v = DIM_VALUE[d.key]
            return (
              <Card key={d.key} className="p-4">
                <div className="flex items-baseline justify-between">
                  <div className="text-sm font-medium">{d.label} <span className="text-xs text-ink-3">· weight {num(d.weight * 100)}%</span></div>
                  <div className={`num text-sm font-semibold ${scoreText(score)}`}>{score.toFixed(0)}</div>
                </div>
                <div className="mt-2"><Meter value={score} tone={toneFor(score)} /></div>
                <div className="mt-2 flex justify-between text-xs">
                  <span className="text-ink-2"><span className="num font-medium text-ink">{v.fmt(v.get(s))}</span> {v.note}</span>
                  <span className="num text-ink-3">panel median {v.fmt(panelMedian(d.key))}</span>
                </div>
                {d.key === 'price_premium' && (
                  <div className="mt-1 text-[11px] text-ink-3">
                    95% CI {pct(s.premium_ci_low)} to {pct(s.premium_ci_high)} · {s.premium_significant ? 'statistically established' : 'not distinguishable from zero after correction'}
                  </div>
                )}
                {d.key === 'late_delivery' && (
                  <div className="mt-1 text-[11px] text-ink-3">{pct(s.late_orders_pct, 0)} of orders late at all · worst {s.max_days_late} days</div>
                )}
              </Card>
            )
          })}
        </div>
      </Section>

      {/* arithmetic */}
      <Section eyebrow="Financial impact" title="How the rupee figure is built" lede="Every line can be recomputed from the source CSVs.">
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <tbody className="[&_td]:px-4 [&_td]:py-2.5">
              <Row label="A · Short delivery" hint="Σ invoice_amount_billed − Σ quantity_received × unit_price_quoted" value={s.short_loss} strong />
              <Row label="Customer returns — recorded" hint={`${num(s.returns_recorded, 0)} returns with this supplier on record`} value={s.return_loss_recorded} sub />
              <Row label="Customer returns — inferred" hint={`${num(s.returns_inferred, 1)} expected, from the attribution model’s probabilities`} value={s.return_loss_inferred} sub />
              <Row label="B · Customer returns" hint="Quantity returned × this supplier’s median price for that material" value={s.return_loss} strong />
              <tr className="border-t-2 border-ink/70 bg-surface-2/50"><td className="font-semibold">A + B</td><td className="text-xs text-ink-3">Problem statement formula</td><td className="num text-right font-semibold">{inr(s.rubric_core_total)}</td></tr>
              <Row label="+ Rejected at our inspection" hint={`${num(s.qty_rejected, 1)} MT × quoted price`} value={s.reject_loss} sub />
              <Row label="+ Return handling" hint={`${num(Number(summary.config.handling_factor) * 100)}% of return value — assumption`} value={s.handling_loss} sub />
              <Row label="+ Price premium" hint={s.premium_significant ? 'Statistically established over peers' : `Not established (net ${inrShort(s.premium_net_rs)} vs peers, within noise) — not charged`} value={s.premium_loss} sub />
              <tr className="border-t-2 border-ink/70 bg-surface-2/50"><td className="font-semibold">Total quantified</td><td /><td className="num text-right font-semibold">{inr(s.total_impact)}</td></tr>
            </tbody>
          </table>
        </Card>
      </Section>

      {/* by year */}
      <Section eyebrow="Trend" title="By year" lede="Short delivery, returns and rejections per calendar year.">
        <Card className="p-5">
          <div className="space-y-2">
            {years.map((y) => {
              const parts = [
                { v: y.short_loss, c: 'var(--color-s1)', l: 'Short delivery' },
                { v: y.return_loss, c: 'var(--color-s2)', l: 'Returns' },
                { v: y.reject_loss, c: 'var(--color-s4)', l: 'Rejected' },
              ]
              const total = parts.reduce((a, p) => a + p.v, 0)
              return (
                <div key={y.year} className="grid grid-cols-[3.5rem_1fr_6rem] items-center gap-3">
                  <span className="num text-sm text-ink-2">{y.year}</span>
                  <div className="flex h-4 gap-[2px]">
                    {parts.filter((p) => p.v > 0).map((p) => (
                      <div key={p.l} title={`${p.l}: ${inr(p.v)}`} className="h-full first:rounded-l-[4px] last:rounded-r-[4px]"
                           style={{ width: `${(p.v / maxYear) * 100}%`, background: p.c }} />
                    ))}
                  </div>
                  <span className="num text-right text-sm">{inrShort(total)}</span>
                </div>
              )
            })}
          </div>
          <div className="mt-3 flex gap-4 text-xs text-ink-2">
            {[['Short delivery', 'var(--color-s1)'], ['Returns', 'var(--color-s2)'], ['Rejected', 'var(--color-s4)']].map(([l, c]) => (
              <span key={l} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: c }} />{l}</span>
            ))}
          </div>
        </Card>
      </Section>

      {/* by material */}
      <Section eyebrow="Per material" title="Where it goes wrong"
        lede="The same supplier can be fine on one material and poor on another. Flags mark a rate at least twice the panel’s for that material.">
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Material</th><th className="text-right">Orders</th><th className="text-right">Spend</th>
                <th className="text-right">Short %</th><th className="text-right">Days late</th><th className="text-right">Quality %</th>
                <th className="text-right">Price vs peers</th><th className="text-right">Leakage</th><th className="text-left">Flags</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.material_id} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                  <td className="text-ink">{c.material_id}{c.low_confidence && <span className="ml-1 text-xs text-ink-3">(few orders)</span>}</td>
                  <td className="num text-right text-ink-2">{c.orders}</td>
                  <td className="num text-right text-ink-2">{inrShort(c.spend)}</td>
                  <td className="num text-right text-ink-2">{pct(c.short_delivery_pct, 2)}</td>
                  <td className="num text-right text-ink-2">{num(c.mean_days_late, 1)}</td>
                  <td className="num text-right text-ink-2">{pct(c.quality_rejection_pct, 2)}</td>
                  <td className="num text-right text-ink-2">{c.price_premium_pct == null ? '—' : `${c.price_premium_pct > 0 ? '+' : ''}${pct(c.price_premium_pct)}`}</td>
                  <td className="num text-right text-ink">{inrShort(c.leakage)}</td>
                  <td><div className="flex flex-wrap gap-1">{c.flags.map((f) => <Pill key={f} tone="crit">{DIMENSION_LABEL[f]}</Pill>)}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {replacement && (
        <Section id="replace" eyebrow="D5" title="Alternatives already on the panel"
          lede={`Switching each material to its best alternative would have avoided about ${inrShort(replacement.avoidable_total)} of leakage over the period.`}>
          <div className="grid gap-3 md:grid-cols-2">
            {replacement.materials.map((m) => (
              <Card key={m.material} className="p-4">
                <div className="flex justify-between">
                  <span className="font-medium">{m.material}</span>
                  <span className="num text-xs text-ink-3">{m.orders} orders · {inrShort(m.spend)} · avoidable {inrShort(m.avoidable)}</span>
                </div>
                <div className="mt-2 space-y-1.5">
                  {m.alternatives.map((a) => (
                    <Link key={a.supplier_id} to={`/supplier/${a.supplier_id}`} className="flex items-center justify-between rounded-lg bg-surface-2/60 px-3 py-2 text-sm hover:bg-surface-2">
                      <span>{a.supplier_name} <span className="text-xs text-ink-3">{a.supplier_id}</span></span>
                      <span className="num text-xs text-ink-2">score {a.score.toFixed(0)} · short {pct(a.short_pct, 2)} · {num(a.days_late, 1)}d late · {a.orders} orders</span>
                    </Link>
                  ))}
                  {!m.alternatives.length && <div className="text-xs text-ink-3">No alternative with enough history for this material.</div>}
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* returns */}
      <Section eyebrow="Customer returns" title={`Returns attributed to ${s.supplier_name}`}
        lede="Recorded returns name this supplier on the return note. Inferred returns had no supplier recorded; this supplier is the model’s most likely source.">
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Return</th><th className="text-left">Date</th><th className="text-left">Material</th>
                <th className="text-right">MT</th><th className="text-left">Reason</th><th className="text-left">Source</th><th className="text-right">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {myReturns.slice(0, 60).map((r) => (
                <tr key={r.return_id} className="border-t border-line [&_td]:px-3 [&_td]:py-1.5">
                  <td className="num text-ink-2">{r.return_id}</td>
                  <td className="num text-ink-2">{date(r.return_date)}</td>
                  <td className="text-ink-2">{r.material_id}</td>
                  <td className="num text-right text-ink-2">{num(r.quantity_returned, 2)}</td>
                  <td className="text-ink-2">{r.reason}</td>
                  <td>{r.source === 'recorded' ? <Pill>Recorded</Pill> : <Pill tone="accent">Inferred</Pill>}</td>
                  <td className="num text-right text-ink-2">{r.source === 'recorded' ? '—' : pct(r.confidence * 100, 0)}</td>
                </tr>
              ))}
              {!myReturns.length && <tr><td colSpan={7} className="px-3 py-6 text-center text-ink-3">No returns attributed.</td></tr>}
            </tbody>
          </table>
        </div>
        {myReturns.length > 60 && <div className="mt-2 text-xs text-ink-3">Showing 60 of {myReturns.length}.</div>}
      </Section>
    </div>
  )
}

function Row({ label, hint, value, strong, sub }: { label: string; hint: string; value: number; strong?: boolean; sub?: boolean }) {
  return (
    <tr className="border-t border-line first:border-t-0">
      <td className={strong ? 'font-medium text-ink' : sub ? 'pl-8 text-ink-2' : ''}>{label}</td>
      <td className="font-mono text-[11px] text-ink-3">{hint}</td>
      <td className={`num text-right ${strong ? 'font-medium text-ink' : 'text-ink-2'}`}>{inr(value)}</td>
    </tr>
  )
}
