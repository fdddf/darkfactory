import type { ReactNode } from 'react'
import { VERDICT_CHIP } from './ui'

export const STAGES = ['precheck', 'blackbox', 'oracle', 'inspection', 'brief', 'deploy'] as const
export type StageName = (typeof STAGES)[number]

/** What each gate is actually for, shown under its name. */
const CAPTION: Record<StageName, string> = {
  precheck: 'reproduce it',
  blackbox: 'propose a fix',
  oracle: 'behaviour holds',
  inspection: 'change is safe',
  brief: 'research it',
  deploy: 'flag + canary',
}

const NODE: Record<string, string> = {
  allow: 'border-verdict-allow bg-verdict-allow text-white',
  reject: 'border-verdict-reject bg-verdict-reject text-white',
  escalate: 'border-verdict-escalate bg-verdict-escalate text-white',
  researched: 'border-verdict-info bg-verdict-info text-white',
  produced: 'border-line-strong bg-surface text-muted-fg',
  run: 'border-verdict-info bg-wash-info text-verdict-info',
  idle: 'border-line bg-surface text-faint',
}
// Written out rather than derived. Tailwind only ships classes it can see
// in the source, so a name built at runtime may have no CSS behind it.
const WORD: Record<string, string> = {
  allow: 'text-verdict-allow',
  reject: 'text-verdict-reject',
  escalate: 'text-verdict-escalate',
  researched: 'text-verdict-info',
  produced: 'text-muted-fg',
}
const RAIL: Record<string, string> = {
  allow: 'bg-verdict-allow',
  reject: 'bg-verdict-reject',
  escalate: 'bg-verdict-escalate',
  researched: 'bg-verdict-info',
  produced: 'bg-line-strong',
  run: 'bg-verdict-info',
}

function Tick({ done }: { done: boolean }) {
  return done
    ? <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="currentColor"
           strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 8.5l3.2 3.2L13 5" />
      </svg>
    : null
}

/**
 * The line, drawn flat.
 *
 * A fixed-height rail with one node per gate beats a 3D stage here: the
 * layout is the same at every window size, and the thing a viewer needs to
 * read — which gate stopped the fix — is the largest element on screen.
 */
export default function Pipeline({
  stages, outcome, stoppedAt, title, subtitle, verdict,
}: {
  stages: Record<string, string>
  outcome: string | null
  /** The gate that refused, as the line reported it. Later gates may still
      have run: research happens after a refusal, not before it. */
  stoppedAt: string | null
  title: ReactNode
  subtitle: ReactNode
  verdict: { decision: string; reason: string } | null
}) {
  const stopped = outcome && outcome !== 'allow'

  return (
    <div className="px-7 py-6">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <div className="text-[17px] font-semibold tracking-tight truncate">{title}</div>
          <div className="text-[11.5px] text-muted-fg mt-1 truncate">{subtitle}</div>
        </div>
        {verdict && (
          <div className="text-right shrink-0 max-w-[34ch]">
            <span className={`inline-block px-2.5 py-1 rounded-full ring-1 text-[11px]
                              font-bold uppercase tracking-[0.12em]
                              ${VERDICT_CHIP[verdict.decision] ?? ''}`}>
              {verdict.decision === 'allow' ? 'shipped unattended' : verdict.decision}
            </span>
            <div className="text-[11.5px] text-muted-fg mt-1.5">{verdict.reason}</div>
          </div>
        )}
      </div>

      {/* rail + gates */}
      <div className="relative mt-9 mb-2">
        <div className="absolute left-[7%] right-[7%] top-5 h-0.5 bg-line rounded-full" />

        <div className="relative grid grid-cols-6">
          {STAGES.map((name, i) => {
            const v = stages[name] ?? ''
            const state = v || 'idle'
            const prev = i > 0 ? stages[STAGES[i - 1]] : null
            const settled = v && v !== 'run'

            return (
              <div key={name} className="relative flex flex-col items-center">
                {/* the segment of rail that leads into this gate */}
                {i > 0 && (
                  <span
                    className={`absolute top-5 right-1/2 left-[-50%] h-0.5 origin-left
                                transition-all duration-500
                                ${prev ? RAIL[prev] ?? 'bg-line-strong' : 'bg-line'}`}
                  />
                )}

                <span
                  className={`relative z-10 w-10 h-10 rounded-full border-2 grid place-items-center
                              transition-all duration-300 shadow-card
                              ${NODE[state] ?? NODE.idle}
                              ${v === 'run' ? 'scale-110 ring-4 ring-verdict-info/15' : ''}`}
                >
                  {v === 'run'
                    ? <i className="w-2 h-2 rounded-full bg-verdict-info animate-pulse" />
                    : settled
                      ? <Tick done />
                      : <i className="w-1.5 h-1.5 rounded-full bg-line-strong" />}
                </span>

                <span className={`mt-2.5 text-[11px] font-semibold tracking-tight
                                  ${v ? 'text-head' : 'text-faint'}`}>
                  {name}
                </span>
                <span className="text-[10px] text-faint">{CAPTION[name]}</span>
                <span className={`mt-1 text-[10px] font-semibold uppercase tracking-[0.1em]
                                  ${settled ? WORD[v] ?? 'text-muted-fg' : 'text-transparent'}`}>
                  {settled ? v : '·'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* where the work ended up */}
      <div className="grid grid-cols-2 gap-3 mt-7">
        <div className={`rounded-lg border px-4 py-3 transition
                         ${outcome === 'allow'
                           ? 'border-verdict-allow bg-wash-allow'
                           : 'border-line bg-sunken opacity-55'}`}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em]
                          text-verdict-allow">shipped</div>
          <div className="text-[11.5px] text-muted-fg mt-0.5">
            {outcome === 'allow'
              ? 'deployed behind a flag, no human approved it'
              : 'every interlock has to clear first'}
          </div>
        </div>

        <div className={`rounded-lg border px-4 py-3 transition
                         ${stopped
                           ? (outcome === 'reject'
                               ? 'border-verdict-reject bg-wash-reject'
                               : 'border-verdict-escalate bg-wash-escalate')
                           : 'border-line bg-sunken opacity-55'}`}>
          <div className={`text-[11px] font-semibold uppercase tracking-[0.12em]
                           ${outcome === 'reject' ? 'text-verdict-reject' : 'text-verdict-escalate'}`}>
            handed to a human
          </div>
          <div className="text-[11.5px] text-muted-fg mt-0.5">
            {stopped
              ? `refused at ${stoppedAt ?? 'a gate'}; nothing shipped`
              : 'anything that is not a clear pass comes here'}
          </div>
        </div>
      </div>
    </div>
  )
}
