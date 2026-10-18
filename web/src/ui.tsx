import type { ReactNode } from 'react'
import type { Decision, Severity } from './types'

export const VERDICT: Record<string, string> = {
  allow: 'text-verdict-allow',
  reject: 'text-verdict-reject',
  escalate: 'text-verdict-escalate',
  researched: 'text-verdict-info',
  produced: 'text-muted-fg',
  accepted: 'text-muted-fg',
}
export const VERDICT_BG: Record<string, string> = {
  allow: 'bg-verdict-allow',
  reject: 'bg-verdict-reject',
  escalate: 'bg-verdict-escalate',
  researched: 'bg-verdict-info',
  produced: 'bg-line-strong',
  accepted: 'bg-line-strong',
}
export const VERDICT_CHIP: Record<string, string> = {
  allow: 'bg-wash-allow text-verdict-allow ring-verdict-allow/20',
  reject: 'bg-wash-reject text-verdict-reject ring-verdict-reject/20',
  escalate: 'bg-wash-escalate text-verdict-escalate ring-verdict-escalate/20',
  researched: 'bg-wash-info text-verdict-info ring-verdict-info/20',
  produced: 'bg-sunken text-muted-fg ring-line-strong/60',
  accepted: 'bg-sunken text-muted-fg ring-line-strong/60',
}

export const SEV_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
export const SEV: Record<Severity, string> = {
  critical: 'border-verdict-reject bg-wash-reject',
  high: 'border-verdict-escalate bg-wash-escalate',
  medium: 'border-line-strong bg-sunken',
  low: 'border-line-strong bg-sunken',
  info: 'border-line bg-sunken',
}
export const SEV_TEXT: Record<Severity, string> = {
  critical: 'text-verdict-reject',
  high: 'text-verdict-escalate',
  medium: 'text-body',
  low: 'text-muted-fg',
  info: 'text-faint',
}

export const label = 'text-[10px] font-semibold uppercase tracking-[0.12em] text-faint'

export function Card({ title, extra, children, className = '', pad = true }: {
  title?: ReactNode; extra?: ReactNode; children: ReactNode
  className?: string; pad?: boolean
}) {
  return (
    <section className={`bg-surface border border-line rounded-lg shadow-card ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 px-4 h-11 border-b border-line">
          <h2 className={label}>{title}</h2>
          {extra}
        </header>
      )}
      <div className={pad ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

export function Stat({ label: text, value, tone = '', hint }: {
  label: string; value: ReactNode; tone?: string; hint?: ReactNode
}) {
  return (
    <div className="bg-surface border border-line rounded-lg shadow-card px-4 py-3.5">
      <div className={label}>{text}</div>
      <div className={`mono text-[26px] leading-none mt-2 tabular-nums ${tone || 'text-head'}`}>
        {value}
      </div>
      {hint && <div className="text-[10.5px] text-faint mt-1.5">{hint}</div>}
    </div>
  )
}

export function Badge({ kind, children }: { kind?: Decision | string; children: ReactNode }) {
  const chip = kind ? VERDICT_CHIP[kind] ?? 'bg-sunken text-muted-fg ring-line-strong/60'
                    : 'bg-sunken text-muted-fg ring-line-strong/60'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ring-1
                      text-[10px] font-semibold uppercase tracking-[0.1em] ${chip}`}>
      {children}
    </span>
  )
}

export function Dot({ kind }: { kind?: string }) {
  return <i className={`inline-block w-1.5 h-1.5 rounded-full shrink-0
                        ${kind ? VERDICT_BG[kind] ?? 'bg-line-strong' : 'bg-line-strong'}`} />
}

export function Button({ tone = 'default', className = '', ...rest }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'default' | 'go' | 'warn' | 'ghost' }) {
  const tones = {
    default: 'bg-surface border-line-strong text-body hover:bg-sunken hover:text-head shadow-card',
    ghost: 'bg-transparent border-transparent text-muted-fg hover:bg-sunken hover:text-head',
    go: 'bg-verdict-info border-verdict-info text-white hover:brightness-110 shadow-card',
    warn: 'bg-surface border-verdict-escalate/45 text-verdict-escalate hover:bg-wash-escalate shadow-card',
  }
  return (
    <button
      {...rest}
      className={`px-3 py-1.5 rounded-md border text-[11.5px] font-medium transition
                  disabled:opacity-40 disabled:cursor-default disabled:hover:bg-surface
                  ${tones[tone]} ${className}`}
    />
  )
}

export function Field({ label: text, hint, ...rest }:
  React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block">
      <span className={`block ${label} mb-1.5`}>{text}</span>
      <input
        {...rest}
        className="w-full bg-surface border border-line-strong rounded-md px-3 py-2 text-[12.5px]
                   text-head placeholder:text-faint outline-none transition
                   focus:border-verdict-info focus:ring-2 focus:ring-verdict-info/15"
      />
      {hint && <span className="block text-[10.5px] text-faint mt-1">{hint}</span>}
    </label>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="text-faint text-[12px] py-8 text-center">{children}</div>
}

/** Unified diff with the lines that drove a verdict picked out. */
export function Diff({ text, highlight = [] }: { text: string; highlight?: string[] }) {
  if (!text) return <Empty>no diff</Empty>
  return (
    <pre className="bg-sunken border border-line rounded-md overflow-x-auto
                    text-[11.5px] leading-[1.65] py-2">
      {text.split('\n').map((l, i) => {
        const hot = highlight.some((h) => h && l.includes(h))
        let tone = 'text-body'
        let wash = ''
        if (/^(diff|index|---|\+\+\+|@@)/.test(l)) tone = 'text-faint'
        else if (l.startsWith('+')) { tone = 'text-verdict-allow'; wash = 'bg-wash-allow' }
        else if (l.startsWith('-')) { tone = 'text-verdict-reject'; wash = 'bg-wash-reject' }
        return (
          <div
            key={i}
            className={`px-3 ${tone} ${wash}
                        ${hot ? 'bg-verdict-reject/15 font-semibold border-l-2 border-verdict-reject pl-[10px]' : ''}`}
          >
            {l || ' '}
          </div>
        )
      })}
    </pre>
  )
}

/** A horizontal meter for a count against the biggest count in its group. */
export function Meter({ value, max, tone }: { value: number; max: number; tone: string }) {
  return (
    <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
      <div className={`h-full rounded-full ${tone}`}
           style={{ width: `${max ? Math.max(6, (value / max) * 100) : 0}%` }} />
    </div>
  )
}

export const ago = (ts?: number | null) => {
  if (!ts) return '—'
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}
