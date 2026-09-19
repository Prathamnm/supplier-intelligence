/** The app's small bar-chart mark, shared by the header and the start page. */
export function BrandMark() {
  return (
    <span className="grid size-7 place-items-center rounded-lg bg-surface-2 ring-1 ring-line">
      <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
        <rect x="2" y="9" width="3" height="5" rx="1" fill="var(--color-crit)" />
        <rect x="6.5" y="5" width="3" height="9" rx="1" fill="var(--color-ink-3)" />
        <rect x="11" y="2" width="3" height="12" rx="1" fill="var(--color-ink-3)" />
      </svg>
    </span>
  )
}
