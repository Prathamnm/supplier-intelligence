import { useCallback, useEffect, useRef, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { analyseSample, ApiError, createAnalysis, getSamples, getSchema, type Sample, type Schema } from '../lib/api'
import { useDatasetState } from '../lib/dataset'
import { Card, Pill, Section } from '../components/ui'

const FILE_LABEL: Record<string, string> = {
  purchase_orders: 'Purchase orders',
  goods_receipts: 'Goods receipts',
  customer_returns: 'Customer returns',
  market_price_index: 'Market price index',
  payment_records: 'Payment records',
  supplier_master: 'Supplier master',
}

interface Picked {
  file: File
  detected: string | null
  columns: string[]
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading'; fraction: number }
  | { kind: 'analysing'; label: string; started: number }
  | { kind: 'error'; message: string }

/** Header row of a CSV, read from the first few KB only. */
async function readHeader(file: File): Promise<string[]> {
  const head = await file.slice(0, 64 * 1024).text()
  const line = head.replace(/^\uFEFF/, '').split(/\r?\n/, 1)[0] ?? ''
  const cols: string[] = []
  let cur = ''
  let quoted = false
  for (const ch of line) {
    if (ch === '"') quoted = !quoted
    else if (ch === ',' && !quoted) {
      cols.push(cur.trim())
      cur = ''
    } else cur += ch
  }
  cols.push(cur.trim())
  return cols.filter(Boolean)
}

/** Same rule as pipeline/load.py: the first file type whose required columns are all present. */
function identify(columns: string[], schema: Schema): string | null {
  const have = new Set(columns)
  for (const [name, required] of Object.entries(schema.files)) {
    if (required.every((c) => have.has(c))) return name
  }
  return null
}

const kb = (n: number) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} KB`)

export default function Upload() {
  const nav = useNavigate()
  const { activate } = useDatasetState()
  const [schema, setSchema] = useState<Schema | null>(null)
  const [samples, setSamples] = useState<Sample[]>([])
  const [server, setServer] = useState<'checking' | 'up' | 'down'>('checking')
  const [picked, setPicked] = useState<Picked[]>([])
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [elapsed, setElapsed] = useState(0)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    Promise.all([getSchema(), getSamples()])
      .then(([s, samp]) => {
        setSchema(s)
        setSamples(samp)
        setServer('up')
      })
      .catch(() => setServer('down'))
  }, [])

  // A ticking clock while the server analyses, so the wait reads as progress.
  useEffect(() => {
    if (phase.kind !== 'analysing') return
    const t = setInterval(() => setElapsed((Date.now() - phase.started) / 1000), 200)
    return () => clearInterval(t)
  }, [phase])

  const add = useCallback(async (files: FileList | File[]) => {
    if (!schema) return
    const next = await Promise.all(
      Array.from(files).map(async (file) => {
        const columns = file.name.toLowerCase().endsWith('.csv') ? await readHeader(file) : []
        return { file, columns, detected: columns.length ? identify(columns, schema) : null }
      }),
    )
    setPicked((prev) => {
      // A newly added file replaces an earlier one of the same type or name.
      const keep = prev.filter((p) => !next.some((n) => n.file.name === p.file.name || (n.detected && n.detected === p.detected)))
      return [...keep, ...next]
    })
    setPhase({ kind: 'idle' })
  }, [schema])

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) void add(e.dataTransfer.files)
  }

  const required = schema ? Object.keys(schema.files) : Object.keys(FILE_LABEL)
  const found = new Map(picked.filter((p) => p.detected).map((p) => [p.detected as string, p]))
  const missing = required.filter((r) => !found.has(r))
  const tooBig = schema ? picked.filter((p) => p.file.size > schema.max_file_mb * 1e6) : []
  const busy = phase.kind === 'uploading' || phase.kind === 'analysing'
  const ready = server === 'up' && missing.length === 0 && tooBig.length === 0 && !busy

  async function finish(id: string) {
    await activate(id)
    nav('/')
  }

  async function run() {
    const files = required.map((r) => found.get(r)!.file)
    try {
      setPhase({ kind: 'uploading', fraction: 0 })
      const meta = await createAnalysis(files, (fraction) => {
        if (fraction < 1) setPhase({ kind: 'uploading', fraction })
        else setPhase({ kind: 'analysing', label: 'Analysing your data', started: Date.now() })
      })
      await finish(meta.id)
    } catch (e) {
      setPhase({ kind: 'error', message: e instanceof ApiError ? e.message : 'Something went wrong.' })
    }
  }

  async function runSample(s: Sample) {
    try {
      setPhase({ kind: 'analysing', label: `Generating and analysing “${s.title}”`, started: Date.now() })
      const meta = await analyseSample(s.name)
      await finish(meta.id)
    } catch (e) {
      setPhase({ kind: 'error', message: e instanceof ApiError ? e.message : 'Something went wrong.' })
    }
  }

  return (
    <div className="space-y-12">
      <section className="animate-fade">
        <div className="text-xs font-medium uppercase tracking-[.14em] text-ink-3">Check your own suppliers</div>
        <h1 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">Upload your six files. Get the same analysis for your suppliers.</h1>
        <p className="mt-4 max-w-3xl text-base leading-relaxed text-ink-2">
          Scores, money lost, traced returns and negotiation briefs — worked out from your purchase orders, deliveries, payments and
          returns. File names don’t matter; each file is recognised by its columns. Excel and Tally exports work as they are.
        </p>
      </section>

      {server === 'down' && (
        <Card className="border-warn/40 p-5">
          <div className="font-medium text-warn">The analysis server isn’t reachable.</div>
          <p className="mt-1 text-sm text-ink-2">
            Uploads need the Python API. Locally, start it from the project folder with{' '}
            <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[12px]">uvicorn api.main:app --port 8000</code>{' '}
            and reload this page. The rest of the site keeps working with the built-in assignment data.
          </p>
        </Card>
      )}

      <Section eyebrow="Step 1" title="Add the files">
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`flex min-h-64 flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
              dragging ? 'border-accent bg-accent/5' : 'border-line-strong bg-surface'
            } ${server !== 'up' ? 'opacity-50' : ''}`}
          >
            <svg viewBox="0 0 24 24" className="size-10 text-ink-3" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
              <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <div className="mt-3 text-base font-medium">Drop your CSV files here</div>
            <div className="mt-1 text-sm text-ink-3">all six at once, or a few at a time</div>
            <button
              type="button"
              disabled={server !== 'up' || busy}
              onClick={() => input.current?.click()}
              className="mt-5 rounded-lg bg-ink px-4 py-2 text-sm font-medium text-bg hover:bg-ink-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Browse files
            </button>
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) void add(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          <Card className="p-5">
            <div className="flex items-baseline justify-between">
              <div className="text-sm font-medium">Required files</div>
              <div className="num text-xs text-ink-3">{required.length - missing.length} / {required.length}</div>
            </div>
            <ul className="mt-3 space-y-2">
              {required.map((r) => {
                const p = found.get(r)
                return (
                  <li key={r} className="flex items-center gap-3 text-sm">
                    <span
                      className={`grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-bold ${p ? 'bg-good/15 text-good' : 'bg-surface-2 text-ink-3'}`}
                      aria-label={p ? 'present' : 'missing'}
                    >
                      {p ? '✓' : ''}
                    </span>
                    <span className={p ? 'text-ink' : 'text-ink-3'}>{FILE_LABEL[r] ?? r}</span>
                    {p && <span className="ml-auto truncate text-xs text-ink-3" title={p.file.name}>{p.file.name}</span>}
                  </li>
                )
              })}
            </ul>
            {schema && missing.length > 0 && picked.length > 0 && (
              <p className="mt-4 text-xs leading-relaxed text-ink-3">
                Missing files are recognised by these columns — {missing.map((m) => (
                  <span key={m} className="block"><span className="text-ink-2">{FILE_LABEL[m]}:</span> {schema.files[m].join(', ')}</span>
                ))}
              </p>
            )}
          </Card>
        </div>

        {picked.length > 0 && (
          <div className="mt-4 overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-surface-2/60 text-[11px] uppercase tracking-[.08em] text-ink-3">
                <tr className="[&_th]:px-3 [&_th]:py-2.5 [&_th]:font-medium">
                  <th className="text-left">File</th><th className="text-right">Size</th><th className="text-left">Recognised as</th><th />
                </tr>
              </thead>
              <tbody>
                {picked.map((p) => (
                  <tr key={p.file.name} className="border-t border-line [&_td]:px-3 [&_td]:py-2">
                    <td className="text-ink">{p.file.name}</td>
                    <td className="num text-right text-ink-2">{kb(p.file.size)}</td>
                    <td>
                      {p.detected ? (
                        <Pill>{FILE_LABEL[p.detected]}</Pill>
                      ) : (
                        <Pill tone="crit">{p.columns.length ? 'Not recognised — columns don’t match any required file' : 'Not a CSV'}</Pill>
                      )}
                      {schema && p.file.size > schema.max_file_mb * 1e6 && <Pill tone="crit">Over {schema.max_file_mb} MB</Pill>}
                    </td>
                    <td className="text-right">
                      <button
                        onClick={() => setPicked((prev) => prev.filter((x) => x !== p))}
                        disabled={busy}
                        className="text-xs text-ink-3 hover:text-crit"
                        aria-label={`Remove ${p.file.name}`}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section eyebrow="Step 2" title="Run the analysis">
        <Card className="flex flex-wrap items-center gap-4 p-5">
          <button
            onClick={run}
            disabled={!ready}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-white hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Analyse {picked.length ? `${Math.min(found.size, required.length)} files` : ''}
          </button>
          <div className="min-w-0 flex-1 text-sm" aria-live="polite">
            {phase.kind === 'idle' && (
              <span className="text-ink-3">
                {missing.length ? `Add the ${missing.length} missing file${missing.length === 1 ? '' : 's'} to continue.` : 'Ready.'}
              </span>
            )}
            {phase.kind === 'uploading' && (
              <div>
                <div className="text-ink-2">Uploading… {Math.round(phase.fraction * 100)}%</div>
                <div className="mt-1.5 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${phase.fraction * 100}%` }} />
                </div>
              </div>
            )}
            {phase.kind === 'analysing' && (
              <div className="flex items-center gap-3 text-ink-2">
                <span className="size-4 animate-spin rounded-full border-2 border-accent border-t-transparent" aria-hidden />
                {phase.label}… <span className="num text-ink-3">{elapsed.toFixed(1)}s</span>
              </div>
            )}
            {phase.kind === 'error' && (
              <div className="rounded-lg border border-crit/40 bg-crit/10 px-3 py-2 text-crit">{phase.message}</div>
            )}
          </div>
        </Card>
      </Section>

      {samples.length > 0 && (
        <Section eyebrow="No files to hand?" title="Try a sample"
          lede="Made-up data in the same format, each with some problem suppliers hidden in it. See whether the analysis finds them.">
          <div className="grid gap-3 md:grid-cols-2">
            {samples.map((s) => (
              <Card key={s.name} className="flex flex-col p-4">
                <div className="flex items-baseline justify-between gap-2">
                  <div className="font-medium">{s.title}</div>
                  <div className="num text-xs text-ink-3">{s.suppliers} suppliers · {s.orders.toLocaleString('en-IN')} orders</div>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-2">{s.purpose}</p>
                <button
                  onClick={() => runSample(s)}
                  disabled={busy}
                  className="mt-3 self-start rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 hover:border-accent hover:text-ink disabled:opacity-40"
                >
                  Analyse this sample
                </button>
              </Card>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}
