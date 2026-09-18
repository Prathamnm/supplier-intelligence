import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { summary } from '../lib/data'
import { ErrorBoundary } from './ErrorBoundary'
import { date } from '../lib/format'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/attribution', label: 'Attribution' },
  { to: '/briefs', label: 'Briefs' },
  { to: '/method', label: 'Method' },
]

export function Layout() {
  const { pathname } = useLocation()
  useEffect(() => window.scrollTo(0, 0), [pathname])

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
            <span className="hidden text-xs text-ink-3 sm:inline">Arora Traders</span>
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
          <a href="./approach.pdf" target="_blank" rel="noreferrer"
             className="hidden rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-2 hover:text-ink md:inline-block">
            Write-up (PDF)
          </a>
        </div>
      </header>
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
