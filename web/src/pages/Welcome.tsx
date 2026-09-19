import { useEffect } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import logo from '../assets/mccia-logo-dark.png'
import { BrandMark } from '../components/BrandMark'
import { Stat } from '../components/ui'
import { wakeApi } from '../lib/api'
import { useDataset } from '../lib/dataset'
import { inrShort } from '../lib/format'

const REPO_URL = 'https://github.com/Prathamnm/supplier-intelligence'

export default function Welcome() {
  const { search } = useLocation()
  const { summary, briefs, approachUrl } = useDataset()
  const { counts, totals } = summary

  // The upload API sleeps when idle; start waking it while the visitor reads this page.
  useEffect(() => {
    wakeApi()
  }, [])

  // Older share links (#/?analysis=<id>) go straight to the results.
  if (new URLSearchParams(search).has('analysis')) return <Navigate to={`/overview${search}`} replace />

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-2.5 px-4 sm:px-6">
          <BrandMark />
          <span className="text-sm font-semibold tracking-tight">Supplier Blindspot</span>
          <a href={approachUrl} target="_blank" rel="noreferrer"
             className="ml-auto rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink">
            Write-up (PDF)
          </a>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center px-4 py-16 sm:px-6">
        <section className="animate-fade">
          <img src={logo} alt="MCCIA — Mahratta Chamber of Commerce, Industries and Agriculture" className="h-14 w-auto sm:h-[4.5rem]" />

          <div className="mt-10 text-xs font-medium uppercase tracking-[.14em] text-ink-3">
            MCCIA Applied AI Studio · Problem Statement 4
          </div>
          <h1 className="mt-3 max-w-4xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
            Supplier <span className="text-crit">Blindspot</span>
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-ink-2">
            Find the suppliers quietly costing a business money, put a rupee figure on it, trace the returns nobody recorded, and
            walk into the next negotiation with the evidence.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              to="/overview"
              className="inline-flex items-center gap-2 rounded-lg bg-ink px-5 py-2.5 text-sm font-medium text-bg transition-colors hover:bg-ink-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Get started <span aria-hidden>→</span>
            </Link>
            <Link
              to="/upload"
              className="rounded-lg border border-line px-5 py-2.5 text-sm text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
            >
              Upload your own data
            </Link>
          </div>
        </section>

        <section className="mt-14 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="What's inside">
          <Stat label="Scorecard" value={`${counts.suppliers} suppliers`} sub="Ranked on short and late deliveries, quality and price" />
          <Stat label="Money lost" value={inrShort(totals.total_impact)} sub="From short deliveries, returns and rejected material" />
          <Stat label="Untraced returns" value={`${counts.returns_blank} of ${counts.returns}`} sub="Returns with no supplier, matched to the likely one" />
          <Stat label="Negotiation briefs" value={`${briefs.length} briefs`} sub="One page each, ready to print" />
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-4 py-6 text-xs text-ink-3 sm:px-6">
          <span>MCCIA Applied AI Studio · take-home assignment</span>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-ink">Source code on GitHub</a>
        </div>
      </footer>
    </div>
  )
}
