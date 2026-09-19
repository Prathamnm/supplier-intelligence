import { useEffect } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import logo from '../assets/mccia-logo.png'
import { wakeApi } from '../lib/api'
import { useDatasetState } from '../lib/dataset'

const REPO_URL = 'https://github.com/Prathamnm/supplier-intelligence'

export default function Welcome() {
  const { search } = useLocation()
  const { dataset } = useDatasetState()

  // The upload API sleeps when idle; start waking it while the visitor reads this page.
  useEffect(() => {
    wakeApi()
  }, [])

  // Older share links (#/?analysis=<id>) go straight to the results.
  if (new URLSearchParams(search).has('analysis')) return <Navigate to={`/overview${search}`} replace />

  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden px-4 py-12">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklab,var(--color-accent)_14%,transparent),transparent_60%)]"
      />

      <div className="relative flex w-full max-w-xl animate-fade flex-col items-center text-center">
        <div className="rounded-2xl bg-white px-6 py-5 sm:px-8 sm:py-6 shadow-lg ring-1 ring-black/5">
          <img src={logo} alt="MCCIA — Mahratta Chamber of Commerce, Industries and Agriculture" className="h-16 w-auto sm:h-24" />
        </div>

        <div className="mt-10 text-xs font-medium uppercase tracking-[.16em] text-ink-3">
          MCCIA Applied AI Studio · Problem Statement 4
        </div>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">Supplier Blindspot</h1>
        <p className="mt-4 max-w-md text-base leading-relaxed text-ink-2">
          Find the suppliers quietly costing a business money, put a rupee figure on it, and walk into the next negotiation
          with the evidence.
        </p>

        <Link
          to="/overview"
          className="mt-9 inline-flex items-center gap-2 rounded-xl bg-accent px-7 py-3 text-base font-medium text-white shadow-lg shadow-accent/20 transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Get started
          <span aria-hidden>→</span>
        </Link>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-ink-3">
          <a href={dataset.approachUrl} target="_blank" rel="noreferrer" className="hover:text-ink">
            Read the approach (PDF)
          </a>
          <span aria-hidden>·</span>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-ink">
            Source code
          </a>
        </div>
      </div>
    </main>
  )
}
