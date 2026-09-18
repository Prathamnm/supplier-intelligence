import { Link } from 'react-router-dom'
import { useDataset } from '../lib/dataset'
import { inrShort } from '../lib/format'
import { Card, Pill, Section } from '../components/ui'

export default function Briefs() {
  const { briefs, briefUrl } = useDataset()
  return (
    <div className="space-y-10">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">D4 · Negotiation briefs</div>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">{briefs.length} negotiation briefs, two A4 pages each, ready to print.</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          Page one is what Kiran carries into the room: the rupee figure with its arithmetic, numbered asks with the evidence behind each,
          and what the supplier is likely to say back. Page two lists the purchase orders to put on the table and a per-material breakdown.
          Only recorded returns are claimed; inferred returns are shown as an estimate.
        </p>
      </section>

      <Section title={`Bottom ${briefs.length} by scorecard`}>
        <div className="grid gap-3 md:grid-cols-2">
          {briefs.map((b) => (
            <Card key={b.supplier_id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <Link to={`/supplier/${b.supplier_id}`} className="text-base font-semibold hover:text-accent">{b.supplier_name}</Link>
                  <div className="num text-xs text-ink-3">{b.supplier_id} · rank {b.rank} of {b.n_suppliers} · score {b.score.toFixed(0)}</div>
                </div>
                <div className="flex items-center gap-2">
                  {b.replace && <Pill tone="crit">Replace</Pill>}
                  {b.files.pages != null && <Pill>{b.files.pages} pages</Pill>}
                </div>
              </div>
              <div className="num mt-3 text-2xl font-semibold">{inrShort(b.money.total_impact as number)}</div>
              <div className="text-xs text-ink-3">quantified over {b.period}</div>
              <ol className="mt-4 space-y-2.5 border-t border-line pt-3">
                {b.asks.map((a, i) => (
                  <li key={a.topic} className="grid grid-cols-[1.25rem_1fr] gap-2 text-sm">
                    <span className="num grid size-5 place-items-center rounded-full bg-surface-2 text-[11px] font-semibold text-ink">{i + 1}</span>
                    <span className="text-ink-2"><span className="font-medium text-ink">{a.topic}.</span> {a.ask}</span>
                  </li>
                ))}
              </ol>
              <div className="mt-auto flex gap-2 pt-5">
                {b.files.pdf && (
                  <a href={briefUrl(b.files.pdf)} target="_blank" rel="noreferrer"
                    className="rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-bg hover:bg-ink-2">Download PDF</a>
                )}
                {b.files.html && (
                  <a href={briefUrl(b.files.html)} target="_blank" rel="noreferrer"
                    className="rounded-lg border border-line px-3.5 py-2 text-sm text-ink-2 hover:text-ink">Print view</a>
                )}
              </div>
            </Card>
          ))}
        </div>
      </Section>
    </div>
  )
}
