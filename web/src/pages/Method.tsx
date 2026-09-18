import { useDataset } from '../lib/dataset'
import { inr, num } from '../lib/format'
import { Card, Explain, Pill, Section } from '../components/ui'

// [timing key, step, title, what it does]
const STAGES = [
  ['01 load', '01', 'Read the files', 'Each file is recognised by its columns. Dates and amounts are checked, and the run stops if something is badly wrong.'],
  ['02 prepare', '02', 'Link the records', 'Every purchase order is matched to its delivery and its payment.'],
  ['03 attribute', '03', 'Trace returns', 'Work out the likely supplier behind returns with none recorded.'],
  ['04 money', '04', 'Count the money', 'Money lost on every order: short deliveries, returns and rejections.'],
  ['05 score', '05', 'Score', 'Compare every supplier with a typical one on the four checks.'],
  ['06 validate', '06', 'Double-check', 'Re-rank with different weightings, then compare with the data’s own list of problem suppliers.'],
  ['07 briefs', '07', 'Write the briefs', 'A two-page negotiation brief for each of the worst suppliers.'],
  ['08 export', '08', 'Publish', 'Save the results for this site and as spreadsheets.'],
]

const CHOICES = [
  ['Value of a return', 'The supplier’s usual price for that material. The cost of handling returns (estimated at 15%) is shown separately and kept out of the headline figure.'],
  ['Late delivery', 'Judged on how many days late, on average. Nearly every supplier is a day or two late on most orders, so “how often late” barely tells them apart.'],
  ['Quality', 'Material we rejected at the gate plus material customers sent back, as a share of what the supplier delivered.'],
  ['Price', 'Compared with what other suppliers charged for the same material in the same quarter. Only counted as money lost if the difference is too big to be chance.'],
  ['Our own late payments', 'Worked out from invoice dates and agreed terms. Not scored — shown in each brief because the supplier will probably raise it.'],
  ['Relationship length', 'Deliberately not used: the assignment says scores must be about performance only. A test checks that changing it changes nothing.'],
]

const WEIGHTING_NAME: Record<string, string> = {
  base: 'Our weighting', equal: 'All equal', money_heavy: 'Money first', service_heavy: 'Delivery first', price_heavy: 'Price first',
}

export default function Method() {
  const { quality, summary, byId, dimensionLabel, approachUrl, source } = useDataset()
  const { validation, stability } = summary
  const name = (id: string) => byId.get(id)?.supplier_name ?? id
  const warnings = quality.findings.filter((f) => f.severity !== 'info')
  const routine = quality.findings.filter((f) => f.severity === 'info')

  return (
    <div className="space-y-14">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">How it works</div>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">From six spreadsheets to every number on this site, in seconds.</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          The same steps run on the assignment data and on anything you upload. Nothing is tuned to one dataset — different suppliers,
          materials and file names work without changes.
        </p>
        <a href={approachUrl} target="_blank" rel="noreferrer"
           className="mt-5 inline-block rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-bg hover:bg-ink-2">
          {source === 'bundled' ? 'Read the full approach (PDF)' : 'Read the full approach for this data'}
        </a>
      </section>

      <Section eyebrow="Step by step" title={`What happens in the ${summary.runtime_s.toFixed(0)} seconds`}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map(([key, n, t, d]) => (
            <Card key={n} className="p-4">
              <div className="num text-xs text-ink-3">Step {n}{summary.stage_times[key] != null && ` · ${summary.stage_times[key].toFixed(1)}s`}</div>
              <div className="mt-1 text-sm font-medium">{t}</div>
              <p className="mt-1 text-xs leading-relaxed text-ink-2">{d}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section eyebrow="Double-check" title="Did we find the right suppliers?"
        lede={validation.available && validation.flagged.length
          ? 'The supplier list includes a column marking the known problem suppliers — in effect, the answer. We set it aside, did the whole analysis without it, and only then compared.'
          : 'This data has no list of known problem suppliers to compare against, so the ranking rests on the evidence alone.'}>
        {validation.available && validation.flagged.length > 0 && (
          <div className="grid gap-3 md:grid-cols-3">
            <Card className="p-4">
              <div className="text-xs uppercase tracking-[.1em] text-ink-3">The data’s own list</div>
              <div className="mt-1 text-sm font-medium leading-relaxed">{validation.flagged.map(name).join(', ')}</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-[.1em] text-ink-3">Our bottom {validation.flagged.length}, found without it</div>
              <div className="mt-1 text-sm font-medium leading-relaxed">{validation.our_bottom.map(name).join(', ')}</div>
              <div className="mt-1 text-xs text-good">{validation.hits.length} of {validation.flagged.length} match</div>
            </Card>
            <Card className="p-4">
              <div className="text-xs uppercase tracking-[.1em] text-ink-3">How clear-cut</div>
              <div className="num mt-1 text-lg font-semibold">{validation.gap_to_next != null ? `${num(validation.gap_to_next, 0)} points` : '—'}</div>
              <div className="mt-1 text-xs text-ink-2">between them and the next-worst supplier, on a 100-point score</div>
            </Card>
          </div>
        )}

        <h3 className="mt-8 text-sm font-medium">Does the answer depend on how the checks are weighted?</h3>
        <p className="mt-1 text-sm text-ink-2">
          {stability.stable
            ? `No — the same ${stability.k} suppliers come out at the bottom however the checks are weighted.`
            : `Partly — the bottom ${stability.k} change under some weightings, shown below.`}
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Weighting</th>
                {summary.dimensions.map((d) => <th key={d.key} className="text-right">{dimensionLabel[d.key]}</th>)}
                <th className="text-left">Bottom {stability.k}</th><th className="text-left">Same result?</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stability.scenarios).map(([key, sc]) => (
                <tr key={key} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                  <td className="text-ink">{WEIGHTING_NAME[key] ?? key.replace('_', ' ')}</td>
                  {summary.dimensions.map((d) => <td key={d.key} className="num text-right text-ink-2">{num(sc.weights[d.key] * 100)}%</td>)}
                  <td className="text-ink-2">{sc.bottom.map(name).join(', ')}</td>
                  <td>{sc.same_as_base ? <Pill>✓ Same</Pill> : <Pill tone="crit">Different</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Choices" title="Decisions we made, and why">
        <Card className="divide-y divide-line">
          {CHOICES.map(([k, v]) => (
            <div key={k} className="grid gap-1 px-5 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
              <div className="text-sm font-medium">{k}</div>
              <div className="text-sm leading-relaxed text-ink-2">{v}</div>
            </div>
          ))}
        </Card>
      </Section>

      {summary.index_context.length > 0 && (
        <Section eyebrow="Market prices" title="Why we don’t judge prices against the published index"
          lede={`It covers only ${summary.index_context.length} of ${summary.counts.materials} materials, and where it exists every supplier charges well above it — so it can’t show who is overcharging. Suppliers are compared with each other instead; the index is quoted in briefs for reference.`}>
          <div className="overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                  <th className="text-left">Material</th><th className="text-right">Published price ({summary.index_context[0]?.index_month})</th>
                  <th className="text-right">What suppliers charge</th><th className="text-right">Difference</th><th className="text-left">Used</th>
                </tr>
              </thead>
              <tbody>
                {summary.index_context.map((r) => (
                  <tr key={r.material} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                    <td>{r.material}</td>
                    <td className="num text-right text-ink-2">{inr(r.index_price)}</td>
                    <td className="num text-right text-ink-2">{inr(r.panel_median)}</td>
                    <td className="num text-right text-ink-2">{r.panel_vs_index >= 1 ? '+' : ''}{num((r.panel_vs_index - 1) * 100, 0)}%</td>
                    <td>{r.usable ? <Pill>For reference</Pill> : <Pill tone="crit">Ignored — different scale</Pill>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <Section eyebrow="Data quality" title="What we noticed in the data"
        lede={warnings.length
          ? `${warnings.length} thing${warnings.length === 1 ? '' : 's'} worth knowing, and what was done about each. Nothing is changed silently.`
          : 'No problems found. Nothing is changed silently.'}>
        {warnings.length > 0 && (
          <Card className="divide-y divide-line">
            {warnings.map((f) => (
              <div key={`${f.stage}-${f.title}-${f.detail}`} className="px-5 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{f.title}</span>
                  {f.action && <Pill>{f.action}</Pill>}
                </div>
                <div className="mt-0.5 text-sm leading-relaxed text-ink-2">{f.detail}</div>
              </div>
            ))}
          </Card>
        )}
        <Explain label={`Show all ${routine.length} routine checks`}>
          {routine.map((f) => (
            <p key={`${f.stage}-${f.title}-${f.detail}`}><span className="text-ink-2">{f.title}.</span> {f.detail}</p>
          ))}
        </Explain>
      </Section>
    </div>
  )
}
