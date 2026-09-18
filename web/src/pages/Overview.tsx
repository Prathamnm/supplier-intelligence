import { Link } from 'react-router-dom'
import { useDataset } from '../lib/dataset'
import { frac, inrShort, int, num, pct } from '../lib/format'
import { Card, CountUp, Explain, Pill, Section, Stat } from '../components/ui'
import { PanelStrip } from '../components/PanelStrip'
import { ImpactBars, Legend } from '../components/ImpactBars'
import { LeagueTable } from '../components/LeagueTable'

const NUMBER_WORD: Record<number, string> = { 1: 'One', 2: 'Two', 3: 'Three', 4: 'Four', 5: 'Five' }

const yearsText = (y: number) => {
  const r = Math.round(y)
  return Math.abs(y - r) < 0.15 ? `${['zero', 'one', 'two', 'three', 'four', 'five'][r] ?? r} year${r === 1 ? '' : 's'}` : `${y.toFixed(1)} years`
}

export default function Overview() {
  const { summary, suppliers, byId, briefById, dimensionLabel: DIMENSION_LABEL, briefUrl, source } = useDataset()
  const { bottom, totals, counts, validation, attribution, stability } = summary
  const bottomNames = bottom.suppliers.map((id) => byId.get(id)?.supplier_name ?? id)
  // The problem statement's own figures only apply to the assignment data.
  const isAssignment = source === 'bundled'

  return (
    <div className="space-y-14">
      {/* ---------------------------------------------------------- hero */}
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">
          {counts.suppliers} suppliers · {summary.period.years.toFixed(0)} years · {int(counts.orders)} purchase orders
        </div>
        <h1 className="mt-3 max-w-4xl text-3xl font-semibold leading-tight tracking-tight sm:text-5xl">
          {NUMBER_WORD[bottom.suppliers.length] ?? bottom.suppliers.length} suppliers cost {isAssignment ? 'Arora Traders' : 'you'}{' '}
          <span className="text-crit"><CountUp value={bottom.total_impact} format={(x) => inrShort(x)} /></span>{' '}
          over {yearsText(summary.period.years)}.
        </h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          {bottomNames.join(', ')} get {frac(bottom.share_of_spend)} of the orders but cause{' '}
          {frac(bottom.share_of_impact)} of the money lost to short deliveries, customer returns and rejected material.
        </p>
        <div className="mt-8">
          <PanelStrip rows={suppliers} />
        </div>
      </section>

      {/* ---------------------------------------------------------- KPIs */}
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat
          label="Lost to short deliveries and returns"
          value={inrShort(totals.rubric_core_total)}
          sub={<>All {counts.suppliers} suppliers, over {yearsText(summary.period.years)}</>}
        />
        <Stat
          label="Total money lost"
          value={inrShort(totals.total_impact)}
          sub={<>Also counts rejected material and handling returns</>}
        />
        <Stat
          label="Returns with no supplier recorded"
          value={`${counts.returns_blank} of ${counts.returns}`}
          sub={<>Traced to their likely supplier; {frac(1 - attribution.metrics.misallocation)} of the value lands on the right one when tested</>}
        />
        {validation.available && validation.flagged.length > 0 ? (
          <Stat
            tone={validation.precision === 1 ? 'good' : 'default'}
            label="Double-checked"
            value={`${validation.hits.length} of ${validation.flagged.length} match`}
            sub={<>The data’s own list of problem suppliers agrees with ours — and we never looked at it while scoring</>}
          />
        ) : (
          <Stat label="Double-checked" value="n/a" sub={<>This data has no list of known problem suppliers to check against</>} />
        )}
      </section>

      {/* ------------------------------------------------- where it goes */}
      <Section
        eyebrow="Money lost"
        title="Where the money goes"
        lede={`The ${Math.min(12, counts.suppliers)} suppliers who cost the most, split by cause. Hover a bar for the amounts; click a name to see that supplier.`}
      >
        <Card className="p-5">
          <div className="mb-4"><Legend /></div>
          <ImpactBars rows={suppliers} limit={12} />
        </Card>
        <Explain>
          <p>
            <b className="text-ink-2">Short delivery</b> is what a supplier billed minus what actually arrived, at their own price — the
            assignment’s formula, <code className="font-mono">invoice_amount_billed − quantity_received × unit_price_quoted</code>, added up over every order.
          </p>
          <p>
            <b className="text-ink-2">Returns</b> are charged to the supplier named on the return note. For the {counts.returns_blank} returns
            with no supplier written down, the value is shared between the likely suppliers according to how probable each one is.
          </p>
        </Explain>

        <div className={`mt-3 grid gap-3 ${isAssignment ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Avoidable loss from the worst {bottom.suppliers.length}</div>
            <div className="num mt-1 text-xl font-semibold">{inrShort(bottom.excess_per_year)} <span className="text-sm font-normal text-ink-3">a year</span></div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">
              More than an average supplier would lose you on the same orders — {pct(bottom.excess_rate_of_spend * 100, 1)} of what you pay them.
            </p>
          </Card>
          {isAssignment && (
            <Card className="p-4">
              <div className="text-xs uppercase tracking-[.1em] text-ink-3">Matches the assignment’s estimate</div>
              <div className="num mt-1 text-xl font-semibold">{inrShort(bottom.scaled_to_ps_low)} – {inrShort(bottom.scaled_to_ps_high)} <span className="text-sm font-normal text-ink-3">a year</span></div>
              <p className="mt-1 text-xs leading-relaxed text-ink-2">
                At the assignment’s stated ₹70–85 L a month of purchases, the same loss rate gives this — inside its own{' '}
                {inrShort(bottom.ps_estimate_low, 0)}–{inrShort(bottom.ps_estimate_high, 0)} estimate. (The data itself covers {inrShort(counts.monthly_spend)} a month.)
              </p>
            </Card>
          )}
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Overcharging</div>
            <div className="num mt-1 text-xl font-semibold">{summary.premium.significant.length ? inrShort(totals.premium_loss) : '₹0 claimed'}</div>
            <p className="mt-1 text-xs leading-relaxed text-ink-2">
              {summary.premium.significant.length
                ? `Proven for ${summary.premium.significant.map((id) => byId.get(id)?.supplier_name ?? id).join(', ')}: they consistently charge more than others for the same material.`
                : 'Some suppliers look a little pricier, but no difference is big enough to rule out chance — so it isn’t counted as money lost.'}
            </p>
          </Card>
        </div>
      </Section>

      {/* ------------------------------------------------ recommendation */}
      <Section
        eyebrow="Recommendation"
        title={`Replace these ${NUMBER_WORD[summary.replacements.length]?.toLowerCase() ?? summary.replacements.length} — better suppliers are already on your panel`}
        lede={<>
          For each material they supply, the suppliers you already buy from who do it better.{' '}
          {stability.stable
            ? 'The result holds however the four checks are weighted.'
            : 'Which suppliers land at the very bottom depends partly on how the checks are weighted — see Method.'}
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
                    <div className="num text-xs text-ink-3">Score {r.score.toFixed(0)}/100 · {r.rank === counts.suppliers ? 'the lowest' : `${counts.suppliers - r.rank + 1} from the bottom`} of {counts.suppliers}</div>
                  </div>
                  <Pill tone="crit">Replace</Pill>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[.1em] text-ink-3">Money lost</div>
                    <div className="num text-lg font-semibold">{inrShort(r.total_impact)}</div>
                  </div>
                  <div>
                    <div className="text-[11px] uppercase tracking-[.1em] text-ink-3">Saved by switching</div>
                    <div className="num text-lg font-semibold text-good">{inrShort(r.avoidable_total)}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1 text-xs text-ink-3">
                  Weak on {r.drivers.map((d) => <Pill key={d}>{DIMENSION_LABEL[d]}</Pill>)}
                </div>
                <div className="mt-4 space-y-2 border-t border-line pt-3">
                  {r.materials.slice(0, 4).map((m) => (
                    <div key={m.material} className="text-sm">
                      <div className="flex justify-between gap-2">
                        <span className="text-ink">{m.material}</span>
                        <span className="num text-xs text-ink-3">{inrShort(m.spend)} paid</span>
                      </div>
                      <div className="text-xs text-ink-2">
                        Switch to{' '}
                        {m.alternatives.map((a, i) => (
                          <span key={a.supplier_id}>
                            {i > 0 && ' or '}
                            <Link to={`/supplier/${a.supplier_id}`} className="text-ink hover:text-accent">{a.supplier_name}</Link>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                  {r.materials.length > 4 && (
                    <Link to={`/supplier/${r.supplier_id}#replace`} className="text-xs text-accent">+ {r.materials.length - 4} more materials</Link>
                  )}
                </div>
                {b?.files.pdf && (
                  <a href={briefUrl(b.files.pdf)} target="_blank" rel="noreferrer" className="mt-auto pt-4 text-sm font-medium text-accent hover:underline">
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
        eyebrow="All suppliers"
        title="How every supplier scores"
        lede="A score out of 100 from four checks — full quantity, on time, quality and price. Click a supplier to see why they scored as they did."
      >
        <LeagueTable rows={suppliers} />
        <Explain>
          <p>
            The four checks are weighted {Object.entries(summary.weights).map(([k, w]) => `${DIMENSION_LABEL[k].toLowerCase()} ${num(w * 100)}%`).join(', ')}.
            Changing the weights doesn’t change who ends up at the bottom{stability.stable ? '' : ' much'} (see Method).
          </p>
          <p>
            Suppliers with only a few orders are pulled towards the average until they have enough history, so a couple of bad orders
            can’t condemn them. How long a supplier has worked with you is deliberately not part of the score — only how they perform.
          </p>
        </Explain>
      </Section>
    </div>
  )
}
