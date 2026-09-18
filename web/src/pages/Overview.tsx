import { Link } from 'react-router-dom'
import { summary, suppliers, byId, briefById, DIMENSION_LABEL } from '../lib/data'
import { frac, inr, inrShort, int, num, pct } from '../lib/format'
import { Card, CountUp, Pill, Section, Stat } from '../components/ui'
import { PanelStrip } from '../components/PanelStrip'
import { ImpactBars, Legend } from '../components/ImpactBars'
import { LeagueTable } from '../components/LeagueTable'

export default function Overview() {
  const { bottom, totals, counts, validation, attribution, stability } = summary
  const bottomNames = bottom.suppliers.map((id) => byId.get(id)?.supplier_name ?? id)

  return (
    <div className="space-y-14">
      {/* ---------------------------------------------------------- hero */}
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">
          {counts.suppliers} suppliers · {summary.period.years.toFixed(0)} years · {int(counts.orders)} purchase orders
        </div>
        <h1 className="mt-3 max-w-4xl text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
          Three suppliers cost Arora Traders{' '}
          <span className="text-crit"><CountUp value={bottom.total_impact} format={(x) => inrShort(x)} /></span>{' '}
          over three years.
        </h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          {bottomNames.join(', ')} handle {frac(bottom.share_of_spend)} of spend but account for{' '}
          {frac(bottom.share_of_impact)} of every rupee lost to short delivery, customer returns and rejected
          material. Every figure below traces to a purchase order, a goods receipt or a return note.
        </p>
        <div className="mt-8">
          <PanelStrip rows={suppliers} />
        </div>
      </section>

      {/* ---------------------------------------------------------- KPIs */}
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Short delivery + returns"
          value={inrShort(totals.rubric_core_total)}
          sub={<>Across all {counts.suppliers} suppliers, using the problem statement’s formula</>}
        />
        <Stat
          label="Total quantified"
          value={inrShort(totals.total_impact)}
          sub={<>Adds rejected material and return handling</>}
        />
        <Stat
          label="Untraced returns attributed"
          value={`${counts.returns_blank} of ${counts.returns}`}
          sub={<>{frac(attribution.metrics.misallocation, 1)} of value misallocated under cross-validation</>}
        />
        <Stat
          tone={validation.precision === 1 ? 'good' : 'default'}
          label="Blind check"
          value={`${validation.hits.length} / ${validation.flagged.length}`}
          sub={<>Our bottom {validation.flagged.length} match the dataset’s sealed flag, which the scoring never saw</>}
        />
      </section>

      {/* ------------------------------------------------- where it goes */}
      <Section
        eyebrow="D3 · Financial impact"
        title="Where the money goes"
        lede={<>
          Short delivery is the problem statement’s formula verbatim: <code className="rounded bg-surface-2 px-1 font-mono text-[12px]">invoice_amount_billed − quantity_received × unit_price_quoted</code>,
          summed per order. Recorded returns are charged to their supplier; the {counts.returns_blank} untraced returns are split by the attribution model’s probabilities.
        </>}
      >
        <Card className="p-5">
          <div className="mb-4"><Legend /></div>
          <ImpactBars rows={suppliers} limit={12} />
          <div className="mt-4 border-t border-line pt-3 text-xs text-ink-3">
            Top 12 of {counts.suppliers} by total quantified impact. Hover a segment for the rupee breakdown; click a name for the supplier’s page.
          </div>
        </Card>

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Beyond the normal panel rate</div>
            <div className="num mt-1 text-xl font-semibold">{inrShort(bottom.excess_per_year)} <span className="text-sm font-normal text-ink-3">/ year</span></div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">
              What the bottom three leak beyond what the other {counts.suppliers - 3} suppliers leak on the same spend:
              {' '}{pct(bottom.excess_rate_of_spend * 100, 2)} of their spend.
            </p>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Against the problem statement’s estimate</div>
            <div className="num mt-1 text-xl font-semibold">{inrShort(bottom.scaled_to_ps_low)} – {inrShort(bottom.scaled_to_ps_high)} <span className="text-sm font-normal text-ink-3">/ year</span></div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">
              That leakage rate applied to the stated ₹70–85L monthly procurement. The brief estimated
              {' '}{inrShort(bottom.ps_estimate_low, 0)}–{inrShort(bottom.ps_estimate_high, 0)}; the data transacts {inrShort(counts.monthly_spend)} a month, hence the larger absolute figures.
            </p>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Price premium</div>
            <div className="num mt-1 text-xl font-semibold">{summary.premium.significant.length ? inrShort(totals.premium_loss) : '₹0 claimed'}</div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">
              {summary.premium.significant.length
                ? `Established for ${summary.premium.significant.join(', ')}.`
                : `No supplier’s premium over peers survives a ${frac(summary.premium.fdr)} false-discovery test, so none is charged in rupees. Premiums still enter the scorecard, shrunk by their noise.`}
            </p>
          </Card>
        </div>
      </Section>

      {/* ------------------------------------------------ recommendation */}
      <Section
        eyebrow="D5 · Recommendation"
        title="Replace these three — the panel already has better sources"
        lede={<>
          For each material they supply, the best-scoring alternatives already on the panel for that same material.
          The bottom three are unchanged under all {Object.keys(stability.scenarios).length} weightings tested{stability.stable ? '' : ' (not stable — see Method)'}.
        </>}
      >
        <div className="grid gap-3 lg:grid-cols-3">
          {summary.replacements.map((r) => {
            const b = briefById.get(r.supplier_id)
            return (
              <Card key={r.supplier_id} className="flex flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <Link to={`/supplier/${r.supplier_id}`} className="text-base font-semibold hover:text-accent">{r.supplier_name}</Link>
                    <div className="num text-xs text-ink-3">{r.supplier_id} · rank {r.rank} of {counts.suppliers} · score {r.score.toFixed(0)}</div>
                  </div>
                  <Pill tone="crit">Replace</Pill>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[.1em] text-ink-3">Cost to us</div>
                    <div className="num text-lg font-semibold">{inrShort(r.total_impact)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[.1em] text-ink-3">Avoidable by switching</div>
                    <div className="num text-lg font-semibold text-good">{inrShort(r.avoidable_total)}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  {r.drivers.map((d) => <Pill key={d}>{DIMENSION_LABEL[d]}</Pill>)}
                </div>
                <div className="mt-4 space-y-2 border-t border-line pt-3">
                  {r.materials.slice(0, 4).map((m) => (
                    <div key={m.material} className="text-sm">
                      <div className="flex justify-between gap-2">
                        <span className="text-ink">{m.material}</span>
                        <span className="num text-xs text-ink-3">{inrShort(m.spend)} spend</span>
                      </div>
                      <div className="text-xs text-ink-2">
                        → {m.alternatives.map((a) => (
                          <Link key={a.supplier_id} to={`/supplier/${a.supplier_id}`} className="mr-2 hover:text-accent">
                            {a.supplier_name} <span className="text-ink-3">({a.score.toFixed(0)})</span>
                          </Link>
                        ))}
                      </div>
                    </div>
                  ))}
                  {r.materials.length > 4 && (
                    <Link to={`/supplier/${r.supplier_id}#replace`} className="text-xs text-accent">+ {r.materials.length - 4} more materials</Link>
                  )}
                </div>
                {b?.files.pdf && (
                  <a href={`./briefs/${b.files.pdf}`} target="_blank" rel="noreferrer" className="mt-auto pt-4 text-sm font-medium text-accent hover:underline">
                    Open negotiation brief (PDF) →
                  </a>
                )}
              </Card>
            )
          })}
        </div>
      </Section>

      {/* ---------------------------------------------------- scorecard */}
      <Section
        eyebrow="D2 · Scorecard"
        title={`All ${counts.suppliers} suppliers`}
        lede={<>
          Four dimensions, weighted {Object.entries(summary.weights).map(([k, w]) => `${DIMENSION_LABEL[k].toLowerCase()} ${num(w * 100)}%`).join(', ')}.
          Rates are shrunk toward the panel average in proportion to how little evidence a supplier has. Relationship length is not used. Click any row.
        </>}
      >
        <LeagueTable rows={suppliers} />
        <p className="mt-3 text-xs text-ink-3">
          Total quantified across the panel: {inr(totals.total_impact)}.
        </p>
      </Section>
    </div>
  )
}
