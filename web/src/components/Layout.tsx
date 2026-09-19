import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { wakeApi } from '../lib/api'
import { useDatasetState } from '../lib/dataset'
import { ErrorBoundary } from './ErrorBoundary'
import { date } from '../lib/format'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/attribution', label: 'Untraced returns' },
  { to: '/briefs', label: 'Briefs' },
  { to: '/method', label: 'Method' },
  { to: '/upload', label: 'Upload' },
]

export function Layout() {
  const { pathname } = useLocation()
  const { dataset, reset, notice } = useDatasetState()
  const { summary, approachUrl } = dataset
  // Start waking the upload API in the background the moment the site opens.
  useEffect(() => {
    wakeApi()
  }, [])

  // Scroll to the top on every route change. The braces matter: newer browsers
  // make scrollTo() return a Promise, and an effect that returns anything but a
  // cleanup function crashes React on the next navigation (blank page).
  // biome-ignore lint/correctness/useExhaustiveDependencies: pathname is the trigger -- scroll to top on every route change
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2.5">
            <span className="grid size-7 place-items-center rounded-lg bg-surface-2 ring-1 ring-line">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
                <rect x="2" y="9" width="3" height="5" rx="1" fill="var(--color-crit)" />
                <rect x="6.5" y="5" width="3" height="9" rx="1" fill="var(--color-ink-3)" />
                <rect x="11" y="2" width="3" height="12" rx="1" fill="var(--color-ink-3)" />
              </svg>
            </span>
            <span className="text-sm font-semibold tracking-tight">Supplier Blindspot</span>
            {dataset.source === 'bundled' && <span className="hidden text-xs text-ink-3 sm:inline">Arora Traders</span>}
          </NavLink>
          <nav className="-mx-1 flex flex-1 items-center gap-1 overflow-x-auto">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors ${isActive ? 'bg-surface-2 text-ink' : 'text-ink-3 hover:text-ink'}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <a href={approachUrl} target="_blank" rel="noreferrer"
             className="hidden rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink md:inline-block">
            Write-up (PDF)
          </a>
        </div>
      </header>
      {(dataset.source !== 'bundled' || notice) && (
        <div className={`border-b ${notice ? 'border-warn/30 bg-warn/10' : 'border-accent/30 bg-accent/10'}`}>
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm sm:px-6">
            {notice ? (
              <span className="text-warn">{notice}</span>
            ) : (
              <>
                <span className="size-2 rounded-full bg-accent" aria-hidden />
                <span className="text-ink">
                  Viewing <b>{dataset.label}</b>
                </span>
                <span className="text-ink-3">
                  {summary.counts.suppliers} suppliers · {summary.counts.orders.toLocaleString('en-IN')} orders · analysed in{' '}
                  {dataset.meta?.runtime_s?.toFixed(1) ?? '—'}s
                </span>
                <button
                  type="button"
                  onClick={() => navigator.clipboard?.writeText(`${window.location.origin}${window.location.pathname}#/?analysis=${dataset.key}`)}
                  className="ml-auto text-ink-3 hover:text-ink"
                  title="Copy a link that opens this analysis (while the server keeps it)"
                >
                  Copy link
                </button>
                <button type="button" onClick={reset} className="text-accent hover:underline">Back to assignment data</button>
              </>
            )}
          </div>
        </div>
      )}
      <main className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6">
        {/* Keyed by route so navigating away clears a failed view. */}
        <ErrorBoundary key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-4 py-6 text-xs text-ink-3 sm:px-6">
          <span>
            {summary.counts.orders.toLocaleString('en-IN')} purchase orders · {summary.counts.suppliers} suppliers ·{' '}
            {date(summary.period.start)} – {date(summary.period.end)}
          </span>
          <span>Computed by the Python pipeline in {summary.runtime_s.toFixed(1)}s · {summary.generated_at.replace('T', ' ')}</span>
        </div>
      </footer>
    </div>
  )
}
