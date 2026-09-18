import { useDataset } from '../lib/dataset'
import { inr, num } from '../lib/format'
import { Card, Pill, Section } from '../components/ui'

const STAGES = [
  ['01 load', '01', 'Load & validate', 'Identify each CSV by its columns, coerce types, stop on mixed units or missing files. The answer-key column is removed here and sealed.'],
  ['02 prepare', '02', 'Map & join', 'One row per purchase order carrying its receipt, payment and supplier. Every join asserts its row count.'],
  ['03 attribute', '03', 'Attribute returns', 'Score every supplier as the possible source of each untraced return; validate on the traced ones.'],
  ['04 money', '04', 'Convert to rupees', 'The problem statement’s formula per order, return value by probability, peer-benchmarked price premium with a significance test.'],
  ['05 score', '05', 'Score', 'Four rates, shrunk toward the panel by evidence, scored by distance from the typical supplier, weighted.'],
  ['06 validate', '06', 'Validate', 'Re-rank under alternative weightings, then open the sealed answer key once.'],
  ['07 briefs', '07', 'Briefs', 'Compose the asks, render A4 HTML, print to PDF.'],
  ['08 export', '08', 'Export', 'JSON for this site, CSV for spreadsheets.'],
]

const ASSUMPTIONS = [
  ['Return value', 'Quantity returned × the supplier’s own median price for that material. Handling cost (15%) is shown separately and is not part of the headline.'],
  ['Late delivery', 'Scored on average days late. Almost every supplier is late by a day or two on most orders, so the share of late orders barely separates them; both are reported.'],
  ['Quality', 'Material rejected at our inspection plus customer returns attributed to the supplier, as a share of quantity received.'],
  ['Price benchmark', 'Median price other suppliers quoted for the same material in the same quarter. The published index covers 6 of 18 materials and sits well below what the whole panel pays, so it is context only.'],
  ['Payment lateness', 'Recomputed from invoice date + agreed days; the supplied days_late column does not reconcile with the dates. Used only to warn Kiran of the supplier’s likely counter-argument.'],
  ['Time', 'All grouping uses po_date. The year inside po_id disagrees with po_date on most rows and is treated as a label.'],
  ['Relationship length', 'Not read by any scoring code. A test shuffles it and asserts every score is unchanged.'],
]

export default function Method() {
  const { quality, summary, dimensionLabel: DIMENSION_LABEL, approachUrl, source } = useDataset()
  const { validation, stability } = summary
  const sev = { info: 'default', warning: 'crit', error: 'crit' } as const

  return (
    <div className="space-y-14">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">Method & data quality</div>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">One command, eight stages, nothing hard-coded.</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-sm">python -m pipeline.run</code> reads the six CSVs and writes everything on
          this site in {summary.runtime_s.toFixed(1)} seconds. No supplier ID, material name or threshold tuned to this data appears in the code; a different
          dataset with different suppliers and file names runs unchanged (there is a test for it).
        </p>
        <a href={approachUrl} target="_blank" rel="noreferrer"
           className="mt-5 inline-block rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-bg hover:bg-ink-2">
          {source === 'bundled' ? 'Read the approach document (PDF)' : 'Read the approach document for this data'}
        </a>
      </section>

      <Section eyebrow="Pipeline" title="Stages">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map(([key, n, t, d]) => (
            <Card key={n} className="p-4">
              <div className="num text-xs text-ink-3">{n}{summary.stage_times[key] != null && ` · ${summary.stage_times[key].toFixed(2)}s`}</div>
              <div className="mt-1 text-sm font-medium">{t}</div>
              <p className="mt-1 text-xs leading-relaxed text-ink-2">{d}</p>
            </Card>
          ))}
        </div>
      </Section>

      <Section eyebrow="Validation" title="Blind check against the sealed answer key"
        lede={<>
          <code className="font-mono text-[12px]">supplier_master.csv</code> contains an <code className="font-mono text-[12px]">is_underperformer</code> column — the answer.
          It is removed at load time and never reaches scoring. Only after the ranking is frozen is it opened and compared.
        </>}>
        <div className="grid gap-3 md:grid-cols-3">
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Dataset flags</div>
            <div className="mt-1 text-lg font-semibold">{validation.flagged.join(', ')}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Our bottom {validation.flagged.length}, computed without it</div>
            <div className="mt-1 text-lg font-semibold">{validation.our_bottom.join(', ')}</div>
            <div className="mt-1 text-xs text-ink-2">Ranks {Object.entries(validation.flagged_ranks).map(([k, v]) => `${k} #${v}`).join(', ')} of {validation.n_suppliers}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs uppercase tracking-[.1em] text-ink-3">Margin</div>
            <div className="num mt-1 text-lg font-semibold">{validation.gap_to_next != null ? `${num(validation.gap_to_next, 0)} points` : '—'}</div>
            <div className="mt-1 text-xs text-ink-2">Score gap between the bottom three and the next supplier up.</div>
          </Card>
        </div>

        <div className="mt-3 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Weighting</th>
                {summary.dimensions.map((d) => <th key={d.key} className="text-right">{DIMENSION_LABEL[d.key]}</th>)}
                <th className="text-left">Bottom {stability.k}</th><th className="text-left">Same?</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stability.scenarios).map(([name, sc]) => (
                <tr key={name} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                  <td className="text-ink">{name.replace('_', ' ')}</td>
                  {summary.dimensions.map((d) => <td key={d.key} className="num text-right text-ink-2">{num(sc.weights[d.key] * 100)}%</td>)}
                  <td className="num text-ink-2">{sc.bottom.join(', ')}</td>
                  <td>{sc.same_as_base ? <Pill>✓ yes</Pill> : <Pill tone="crit">✗ differs</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Choices" title="Assumptions, stated">
        <Card className="divide-y divide-line">
          {ASSUMPTIONS.map(([k, v]) => (
            <div key={k} className="grid gap-1 px-5 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
              <div className="text-sm font-medium">{k}</div>
              <div className="text-sm leading-relaxed text-ink-2">{v}</div>
            </div>
          ))}
        </Card>
      </Section>

      <Section eyebrow="Context" title="Published market index vs what the panel pays"
        lede="Shown in briefs only where the index is within a plausible band of transacted prices.">
        <div className="overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
              <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                <th className="text-left">Material</th><th className="text-right">Index ({summary.index_context[0]?.index_month})</th>
                <th className="text-right">Panel median</th><th className="text-right">Panel ÷ index</th><th className="text-left">Used</th>
              </tr>
            </thead>
            <tbody>
              {summary.index_context.map((r) => (
                <tr key={r.material} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                  <td>{r.material}</td>
                  <td className="num text-right text-ink-2">{inr(r.index_price)}</td>
                  <td className="num text-right text-ink-2">{inr(r.panel_median)}</td>
                  <td className="num text-right text-ink-2">{r.panel_vs_index.toFixed(2)}×</td>
                  <td>{r.usable ? <Pill>as context</Pill> : <Pill tone="crit">rejected — different scale</Pill>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section eyebrow="Data quality" title={`${quality.findings.length} findings, ${quality.n_warnings} warnings`}
        lede="Everything the pipeline noticed and what it did about it. Nothing is dropped or fixed silently.">
        <Card className="divide-y divide-line">
          {quality.findings.map((f, i) => (
            <div key={i} className="grid gap-1 px-5 py-3 sm:grid-cols-[6.5rem_1fr] sm:gap-4">
              <div className="flex items-start gap-2">
                <span className="num text-xs text-ink-3">{f.stage}</span>
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{f.title}</span>
                  {f.severity !== 'info' && <Pill tone={sev[f.severity]}>{f.severity}</Pill>}
                  {f.action && <span className="text-xs text-ink-3">→ {f.action}</span>}
                </div>
                <div className="mt-0.5 text-sm leading-relaxed text-ink-2">{f.detail}</div>
              </div>
            </div>
          ))}
        </Card>
      </Section>
    </div>
  )
}
