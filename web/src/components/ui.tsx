import { useEffect, useState, type ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-line bg-surface ${className}`}>{children}</div>
  )
}

export function Section({ eyebrow, title, lede, children, id, aside }: {
  eyebrow?: string
  title: string
  lede?: ReactNode
  children: ReactNode
  id?: string
  aside?: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-20 animate-fade">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div className="max-w-3xl">
          {eyebrow && <div className="mb-1 text-xs font-medium uppercase tracking-[.12em] text-ink-3">{eyebrow}</div>}
          <h2 className="text-lg font-semibold tracking-tight text-ink sm:text-xl">{title}</h2>
          {lede && <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{lede}</p>}
        </div>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'default' }: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: 'default' | 'crit' | 'good'
}) {
  const ring = tone === 'crit' ? 'border-crit/40' : tone === 'good' ? 'border-good/40' : 'border-line'
  return (
    <div className={`rounded-xl border ${ring} bg-surface px-4 py-3.5`}>
      <div className="text-[11px] font-medium uppercase tracking-[.1em] text-ink-3">{label}</div>
      <div className="num mt-1 text-2xl font-semibold tracking-tight text-ink">{value}</div>
      {sub && <div className="mt-1 text-xs leading-snug text-ink-2">{sub}</div>}
    </div>
  )
}

const BAND = {
  act: { label: 'Act now', cls: 'bg-crit/15 text-crit ring-crit/30', dot: 'bg-crit' },
  watch: { label: 'Watch', cls: 'bg-warn/15 text-warn ring-warn/30', dot: 'bg-warn' },
  good: { label: 'Good', cls: 'bg-good/12 text-good ring-good/25', dot: 'bg-good' },
} as const

/** Status always ships with a label and a dot shape, never colour alone. */
export function BandBadge({ band }: { band: keyof typeof BAND }) {
  const b = BAND[band]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${b.cls}`}>
      <span className={`size-1.5 rounded-full ${b.dot}`} aria-hidden />
      {b.label}
    </span>
  )
}

export function Pill({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'crit' | 'accent' }) {
  const cls = tone === 'crit' ? 'bg-crit/12 text-crit' : tone === 'accent' ? 'bg-accent/15 text-accent' : 'bg-surface-2 text-ink-2'
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${cls}`}>{children}</span>
}

/**
 * Animates a number up from zero on mount. Honours reduced motion.
 *
 * Every effect run starts its own animation and its cleanup always leaves
 * the final value showing, so an interrupted run (React StrictMode runs
 * effects twice in development; a hidden tab pauses animation frames)
 * can never strand the display at zero.
 */
export function CountUp({ value, format, duration = 900 }: {
  value: number
  format: (x: number) => string
  duration?: number
}) {
  const [shown, setShown] = useState(value)
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf = 0
    const t0 = performance.now()
    const tick = (now: number) => {
      const p = Math.min((now - t0) / duration, 1)
      setShown(value * (1 - Math.pow(1 - p, 3)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      setShown(value)
    }
  }, [value, duration])
  return <span className="num">{format(shown)}</span>
}

/** A floating tooltip that follows the pointer within a relative parent. */
export function Tip({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-20 min-w-44 -translate-x-1/2 -translate-y-[calc(100%+12px)] rounded-lg border border-line-strong bg-surface-2/95 px-3 py-2 text-xs shadow-xl shadow-black/40 backdrop-blur"
      style={{ left: x, top: y }}
    >
      {children}
    </div>
  )
}

export function Meter({ value, tone = 'accent' }: { value: number; tone?: 'accent' | 'crit' | 'warn' | 'good' }) {
  const bg = { accent: 'bg-accent', crit: 'bg-crit', warn: 'bg-warn', good: 'bg-good' }[tone]
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  )
}

export type Tone = 'crit' | 'warn' | 'good'

export const toneFor = (score: number): Tone => (score < 40 ? 'crit' : score < 70 ? 'warn' : 'good')

// Full class names, spelled out so Tailwind's scanner can see them.
const TONE_TEXT: Record<Tone, string> = { crit: 'text-crit', warn: 'text-warn', good: 'text-good' }

/** Text colour class for a 0-100 score. */
export const scoreText = (score: number) => TONE_TEXT[toneFor(score)]
