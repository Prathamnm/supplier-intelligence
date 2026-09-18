import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDataset, useDetail } from '../lib/dataset'
import { DIMENSION_COPY, median, verdict } from '../lib/explain'
import { date, inr, inrShort, num, pct } from '../lib/format'
import type { DimensionKey, Supplier } from '../lib/types'
import { BandBadge, Card, Explain, Meter, Pill, scoreText, Section, Stat, toneFor, Verdict } from '../components/ui'

/** 1 -> "1st", 22 -> "22nd", 13 -> "13th". */
function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

export default function SupplierPage() {
  const { id = '' } = useParams()
  const { summary, suppliers, byId, briefById, dimensionLabel, briefUrl } = useDataset()
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

  const typical = (k: DimensionKey) => median(suppliers.map(DIMENSION_COPY[k].value))
  const { categories, years } = detail?.details[id] ?? { categories: [], years: [] }
  const maxYear = Math.max(...years.map((y) => y.short_loss + y.return_loss + y.reject_loss), 1)
  const handlingPct = num(Number(summary.config.handling_factor) * 100)

  return (
    <div className="space-y-12">
      {/* header */}
      <section className="animate-fade">
        <Link to="/" className="text-xs text-ink-3 hover:text-ink">← All suppliers</Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight">{s.supplier_name}</h1>
              <BandBadge band={s.band} />
              {replacement && <Pill tone="crit">Consider replacing</Pill>}
            </div>
            <div className="num mt-1 text-sm text-ink-3">
              {s.supplier_id} · {s.orders} orders · {inrShort(s.spend)} paid to them over the period
            </div>
          </div>
          {brief && (
            <div className="flex gap-2">
              {brief.files.pdf && (
                <a href={briefUrl(brief.files.pdf)} target="_blank" rel="noreferrer"
                   className="rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-bg hover:bg-ink-2">
                  Negotiation brief (PDF)
                </a>
              )}
              {brief.files.html && (
                <a href={briefUrl(brief.files.html)} target="_blank" rel="noreferrer"
                   className="rounded-lg border border-line px-3.5 py-2 text-sm text-ink-2 hover:text-ink">
                  Open to print
                </a>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Overall score"
          value={<span className={scoreText(s.score)}>{s.score.toFixed(0)}<span className="text-base text-ink-3">/100</span></span>}
          sub={`${ordinal(s.rank)} of ${suppliers.length} suppliers (1st is best)`}
        />
        <Stat label="Money lost to them" value={inrShort(s.total_impact)} sub={`${pct(s.impact_pct_of_spend, 1)} of what we paid them`} />
        <Stat label="Short deliveries + returns" value={inrShort(s.rubric_core_total)} sub="The two losses the assignment asks for" />
        <Stat
          label="Customer returns linked to them"
          value={num(s.returns_recorded + s.returns_inferred, 0)}
          sub={`${num(s.returns_recorded, 0)} on record, ~${num(s.returns_inferred, 0)} more likely theirs`}
        />
      </section>

      {/* the four checks */}
      <Section
        eyebrow="Scorecard"
        title="How they compare with a typical supplier"
        lede="Four checks. Each scores 100 if they’re as good as a typical supplier on the panel, and drops towards 0 the further behind they are."
      >
        <div className="grid gap-3 md:grid-cols-2">
          {summary.dimensions.map((d) => {
            const copy = DIMENSION_COPY[d.key]
            const score = s[`score_${d.key}` as keyof Supplier] as number
            const typ = typical(d.key)
            const v = verdict(d.key, s, typ, score)
            return (
              <Card key={d.key} className="flex flex-col p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-medium text-ink">{copy.question}</div>
                  <div className="shrink-0 text-right">
                    <span className={`num text-lg font-semibold ${scoreText(score)}`}>{score.toFixed(0)}</span>
                    <span className="text-xs text-ink-3">/100</span>
                  </div>
                </div>
                <div className="mt-2"><Meter value={score} tone={toneFor(score)} /></div>
                <div className="mt-3 text-sm">
                  <span className="num font-semibold text-ink">{copy.phrase(copy.value(s))}</span>
                  <span className="text-ink-3"> · {copy.typical(typ)}</span>
                </div>
                {d.key === 'late_delivery' && (
                  <div className="mt-0.5 text-xs text-ink-3">Late on {pct(s.late_orders_pct, 0)} of orders; longest delay {s.max_days_late} days</div>
                )}
                <div className="mt-3"><Verdict tone={v.tone}>{v.text}</Verdict></div>
                <div className="mt-auto pt-1 text-[11px] text-ink-3">Counts for {num(d.weight * 100)}% of the overall score</div>
              </Card>
            )
          })}
        </div>
        <Explain>
          <p>
            “Typical” is the median supplier on the panel. A check’s score falls from 100 to 0 as a supplier moves from typical to
            six “units” worse, where a unit is the normal spread between suppliers — but never smaller than a difference that matters
            commercially (for example a quarter of a percentage point of short delivery, or half a day late).
            So tiny differences don’t count against anyone.
          </p>
          <p>
            Suppliers with few orders are pulled towards the panel average until they have enough history, so a couple of bad orders
            can’t condemn a small supplier. Price is compared with what other suppliers charged for the same material in the same quarter.
            {!s.premium_significant && ` This supplier’s price difference (${pct(s.premium_ci_low)} to ${pct(s.premium_ci_high)} with 95% confidence) is within what chance alone produces, so no money is claimed for it.`}
          </p>
        </Explain>
      </Section>

      {/* money */}
      <Section
        eyebrow="Money lost"
        title={`Where the ${inrShort(s.total_impact)} comes from`}
        lede="Every line is worked out from our purchase orders, goods receipts and customer return notes."
      >
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <tbody className="[&_td]:px-4 [&_td]:py-2.5">
              <Row label="Billed but never delivered" hint={`${num(s.qty_short, 1)} MT short across their orders`} value={s.short_loss} strong />
              <Row label="Returns our records blame on them" hint={`${num(s.returns_recorded, 0)} returns`} value={s.return_loss_recorded} sub />
              <Row label="Returns probably theirs (no supplier recorded)" hint="Our estimate — see Returns" value={s.return_loss_inferred} sub />
              <Row label="Customer returns" hint="Value of the material sent back" value={s.return_loss} strong />
              <tr className="border-t-2 border-ink/70 bg-surface-2/50">
                <td className="font-semibold">Short deliveries + returns</td>
                <td className="text-xs text-ink-3">The figure the assignment asks for</td>
                <td className="num text-right font-semibold">{inr(s.rubric_core_total)}</td>
              </tr>
              <Row label="+ Material we rejected at the gate" hint={`${num(s.qty_rejected, 1)} MT`} value={s.reject_loss} sub />
              <Row label="+ Cost of handling returns" hint={`Estimated at ${handlingPct}% of their value`} value={s.handling_loss} sub />
              <Row
                label="+ Charging more than others"
                hint={s.premium_significant ? 'Proven across their orders' : 'Not counted — could be chance'}
                value={s.premium_loss}
                sub
              />
              <tr className="border-t-2 border-ink/70 bg-surface-2/50">
                <td className="font-semibold">Total money lost</td><td /><td className="num text-right font-semibold">{inr(s.total_impact)}</td>
              </tr>
            </tbody>
          </table>
        </Card>
        <Explain>
          <p>
            Billed but never delivered = what they invoiced minus what actually arrived, at their own quoted price:{' '}
            <code className="font-mono">invoice_amount_billed − quantity_received × unit_price_quoted</code>, added up over every order.
          </p>
          <p>
            A return is valued at this supplier’s usual price for that material. Where no supplier was written on the return, its value is
            split between the likely suppliers according to how probable each is, so no return is counted twice.
          </p>
        </Explain>
      </Section>

      {/* by year */}
      <Section eyebrow="Trend" title="Year by year" lede="Is it getting better or worse?">
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
      <Section
        eyebrow="By material"
        title="Which materials are the problem"
        lede="A supplier can be fine on one material and poor on another. A red tag means they do at least twice as badly as other suppliers on that material."
      >
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Material</th><th className="text-right">Orders</th><th className="text-right">Paid</th>
                <th className="text-right">Short</th><th className="text-right">Days late</th><th className="text-right">Rejected / returned</th>
                <th className="text-right">Price vs others</th><th className="text-right">Money lost</th><th className="text-left">Problems</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.material_id} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                  <td className="text-ink">{c.material_id}{c.low_confidence && <span className="ml-1 text-xs text-ink-3">(few orders)</span>}</td>
                  <td className="num text-right text-ink-2">{c.orders}</td>
                  <td className="num text-right text-ink-2">{inrShort(c.spend)}</td>
                  <td className="num text-right text-ink-2">{pct(c.short_delivery_pct, 1)}</td>
                  <td className="num text-right text-ink-2">{num(c.mean_days_late, 1)}</td>
                  <td className="num text-right text-ink-2">{pct(c.quality_rejection_pct, 1)}</td>
                  <td className="num text-right text-ink-2">{c.price_premium_pct == null ? '—' : `${c.price_premium_pct > 0 ? '+' : ''}${pct(c.price_premium_pct)}`}</td>
                  <td className="num text-right text-ink">{inrShort(c.leakage)}</td>
                  <td><div className="flex flex-wrap gap-1">{c.flags.map((f) => <Pill key={f} tone="crit">{dimensionLabel[f]}</Pill>)}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {replacement && (
        <Section
          id="replace"
          eyebrow="Who could replace them"
          title="Better suppliers you already buy from"
          lede={`For each material, the best-scoring suppliers already on your panel. Buying from them instead would have saved about ${inrShort(replacement.avoidable_total)}.`}
        >
          <div className="grid gap-3 md:grid-cols-2">
            {replacement.materials.map((m) => (
              <Card key={m.material} className="p-4">
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{m.material}</span>
                  <span className="num text-xs text-ink-3">{inrShort(m.spend)} paid · could save {inrShort(m.avoidable)}</span>
                </div>
                <div className="mt-2 space-y-1.5">
                  {m.alternatives.map((a) => (
                    <Link key={a.supplier_id} to={`/supplier/${a.supplier_id}`} className="flex items-center justify-between gap-3 rounded-lg bg-surface-2/60 px-3 py-2 text-sm hover:bg-surface-2">
                      <span>{a.supplier_name}</span>
                      <span className="num text-xs text-ink-2">score {a.score.toFixed(0)} · {pct(a.short_pct, 1)} short · {num(a.days_late, 1)} days late</span>
                    </Link>
                  ))}
                  {!m.alternatives.length && <div className="text-xs text-ink-3">No other supplier has enough history on this material yet.</div>}
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* returns */}
      <Section
        eyebrow="Customer returns"
        title="Returns linked to this supplier"
        lede="“On record” means the return note names them. “Likely” means nobody wrote down a supplier, and this one is the most probable source — the percentage shows how sure we are."
      >
        {!detail ? (
          <Card className="p-6 text-sm text-ink-3">Loading returns…</Card>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                  <th className="text-left">Return</th><th className="text-left">Date</th><th className="text-left">Material</th>
                  <th className="text-right">Tonnes</th><th className="text-left">Customer’s reason</th><th className="text-left">Linked by</th><th className="text-right">How sure</th>
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
                    <td>{r.source === 'recorded' ? <Pill>On record</Pill> : <Pill tone="accent">Likely</Pill>}</td>
                    <td className="num text-right text-ink-2">{r.source === 'recorded' ? 'Certain' : pct(r.confidence * 100, 0)}</td>
                  </tr>
                ))}
                {!myReturns.length && <tr><td colSpan={7} className="px-3 py-6 text-center text-ink-3">No returns linked to this supplier.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {myReturns.length > 60 && <div className="mt-2 text-xs text-ink-3">Showing 60 of {myReturns.length}.</div>}
      </Section>
    </div>
  )
}

function Row({ label, hint, value, strong, sub }: { label: string; hint: string; value: number; strong?: boolean; sub?: boolean }) {
  return (
    <tr className="border-t border-line first:border-t-0">
      <td className={strong ? 'font-medium text-ink' : sub ? 'pl-8 text-ink-2' : ''}>{label}</td>
      <td className="text-xs text-ink-3">{hint}</td>
      <td className={`num text-right ${strong ? 'font-medium text-ink' : 'text-ink-2'}`}>{inr(value)}</td>
    </tr>
  )
}
