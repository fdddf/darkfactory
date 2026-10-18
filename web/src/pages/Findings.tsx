import { useEffect, useMemo, useState } from 'react'
import { api, useAsync, useLineEvents } from '../api'
import { Button, Card, Diff, Empty, SEV, SEV_ORDER, SEV_TEXT } from '../ui'
import type { Brief, Finding, Patch, Severity } from '../types'
import Page from './Page'

function FindingCard({ f }: { f: Finding }) {
  return (
    <div className={`rounded-lg border-l-[3px] border border-line ${SEV[f.severity]} p-3 min-w-0`}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[12px] font-semibold tracking-tight break-words min-w-0">
          {f.name || f.rule}
        </span>
        <span className={`shrink-0 text-[10px] font-bold uppercase tracking-[0.1em]
                          ${SEV_TEXT[f.severity]}`}>
          {f.severity}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
        {f.cwe && (
          <a
            href={`https://cwe.mitre.org/data/definitions/${f.cwe.replace('CWE-', '')}.html`}
            target="_blank" rel="noreferrer"
            className="px-1.5 py-0.5 rounded bg-surface ring-1 ring-line-strong
                       text-[9.5px] font-semibold text-verdict-info hover:underline"
          >
            {f.cwe}
          </a>
        )}
        <span className="px-1.5 py-0.5 rounded bg-surface ring-1 ring-line
                         text-[9.5px] text-muted-fg mono">{f.rule}</span>
        <span className="px-1.5 py-0.5 rounded bg-surface ring-1 ring-line
                         text-[9.5px] text-faint">{f.layer}</span>
      </div>

      <p className="text-[11px] text-body mt-2 break-words">{f.rationale}</p>

      {f.evidence && (
        <code className="block bg-surface ring-1 ring-line rounded mt-2 px-2 py-1.5
                         text-[10.5px] text-head overflow-x-auto whitespace-pre">
          {f.evidence}
        </code>
      )}

      <div className="text-[10px] text-faint mt-1.5 break-all">
        {f.file}{f.line ? `:${f.line}` : ''}
      </div>
    </div>
  )
}

export default function Findings() {
  const { data, reload } = useAsync(() => api.findings(), [])
  const { data: bugs } = useAsync(() => api.bugs(), [])
  const [selected, setSelected] = useState<string | null>(null)
  const [patch, setPatch] = useState<Patch>({})
  const [tab, setTab] = useState<'proposed' | 'reference'>('proposed')
  const [briefs, setBriefs] = useState<Brief[] | null>(null)
  const [searching, setSearching] = useState(false)

  useLineEvents((e) => { if (e.kind === 'scan_done') reload() })

  const byBug = useMemo(() => data ?? {}, [data])
  const ids = useMemo(
    () => Object.keys(byBug).filter((k) => byBug[k]?.length), [byBug])

  useEffect(() => { if (!selected && ids.length) setSelected(ids[0]) }, [ids, selected])
  useEffect(() => {
    setBriefs(null); setTab('proposed')
    if (selected) api.patch(selected).then(setPatch).catch(() => setPatch({}))
  }, [selected])

  const findings: Finding[] = selected ? byBug[selected] ?? [] : []
  const bug = bugs?.find((b) => b.id === selected)
  const sorted = [...findings].sort(
    (a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity))
  const hot = findings.map((f) => f.evidence?.trim()).filter(Boolean) as string[]

  const counts = SEV_ORDER
    .map((s) => ({ s, n: findings.filter((f) => f.severity === s).length }))
    .filter((r) => r.n)

  const lookUp = async () => {
    setSearching(true)
    try { setBriefs((await api.brief(findings)).briefs) } finally { setSearching(false) }
  }

  if (!ids.length) {
    return (
      <Page title="Findings" sub="What the diff inspection layer raised, and the evidence for it.">
        <Card><Empty>no findings — run a scan</Empty></Card>
      </Page>
    )
  }

  return (
    <Page
      title="Findings"
      sub="What the diff inspection layer raised, and the evidence for it."
      actions={<Button onClick={lookUp} disabled={searching}>
        {searching ? 'searching…' : 'look up advisories'}
      </Button>}
    >
      {/* min-w-0 on the content column: a grid track sized 1fr will not
          shrink below its content, and a wide diff would push the page out. */}
      <div className="grid grid-cols-[230px_minmax(0,1fr)] gap-4 items-start">
        <Card title="by bug" pad={false} className="sticky top-[88px]">
          {ids.map((id) => {
            const worst = [...(byBug[id] ?? [])].sort(
              (a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity))[0]
            return (
              <button key={id} onClick={() => setSelected(id)}
                      className={`w-full text-left px-4 py-2.5 border-t border-line first:border-0
                                  transition ${selected === id ? 'bg-wash-info' : 'hover:bg-sunken'}`}>
                <div className={`text-[12px] mono ${selected === id ? 'text-verdict-info font-semibold' : ''}`}>
                  {id}
                </div>
                <div className="text-[10px] text-faint mt-0.5">
                  {byBug[id].length} finding(s) · worst{' '}
                  <span className={SEV_TEXT[worst?.severity as Severity]}>{worst?.severity}</span>
                </div>
              </button>
            )
          })}
        </Card>

        <div className="flex flex-col gap-4 min-w-0">
          {bug && (
            <Card>
              <div className="flex items-start justify-between gap-5">
                <div className="min-w-0">
                  <div className="text-[15px] font-semibold tracking-tight break-words">
                    {bug.title}
                  </div>
                  <div className="text-[10.5px] text-faint mt-1 break-all">{bug.source}</div>
                  <p className="text-[11.5px] text-body mt-2.5 break-words">{bug.body}</p>
                </div>
                <div className="shrink-0 flex gap-1.5">
                  {counts.map(({ s, n }) => (
                    <span key={s} className={`px-2 py-1 rounded-md bg-sunken ring-1 ring-line
                                              text-[10px] font-semibold ${SEV_TEXT[s]}`}>
                      {n} {s}
                    </span>
                  ))}
                </div>
              </div>
            </Card>
          )}

          <Card title={`findings · ${findings.length}`} pad={false}>
            {/* Two columns at desktop width: findings are short and read
                better side by side than as one long scroll. */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3 p-4">
              {sorted.map((f, i) => <FindingCard key={i} f={f} />)}
            </div>
          </Card>

          {briefs && (
            <Card title="advisories">
              {briefs.length === 0 && <Empty>nothing returned</Empty>}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                {briefs.map((b, i) => (
                  <div key={i} className="border border-line bg-sunken rounded-lg p-3 min-w-0">
                    <div className="text-[10px] text-verdict-info mb-1.5 break-words">? {b.query}</div>
                    {b.error
                      ? <div className="text-[11px] text-verdict-escalate break-words">{b.error}</div>
                      : <>
                          <div className="text-[11px] text-body break-words">
                            {b.answer || 'no summary returned'}
                          </div>
                          {b.sources.map((s, j) => (
                            <a key={j} href={s.url} target="_blank" rel="noreferrer"
                               className="block text-[10px] text-verdict-info hover:underline mt-1 truncate">
                              {s.title || s.url}
                            </a>
                          ))}
                        </>}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {patch.proposed && (
            <Card title="patch" pad={false}
                  extra={
                    <div className="flex gap-1">
                      {(['proposed', 'reference'] as const).map((t) => (
                        <button key={t} onClick={() => setTab(t)}
                                disabled={t === 'reference' && !patch.reference}
                                className={`px-2.5 py-1 rounded-md text-[10px] font-medium border
                                  disabled:opacity-30 transition ${tab === t
                                    ? 'bg-wash-info border-verdict-info/35 text-verdict-info'
                                    : 'border-line text-muted-fg hover:text-head'}`}>
                          {t === 'proposed' ? 'proposed' : 'how it was really fixed'}
                        </button>
                      ))}
                    </div>}>
              <div className="p-4 min-w-0">
                <Diff text={(tab === 'proposed' ? patch.proposed : patch.reference) ?? ''}
                      highlight={tab === 'proposed' ? hot : []} />
                {tab === 'reference' && (
                  <p className="text-[10.5px] text-faint mt-2">
                    The commit WordPress actually shipped for this ticket. The refusal
                    comes with the right answer beside it.
                  </p>
                )}
              </div>
            </Card>
          )}

          <Card title="your call">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => selected && api.decide(selected, 'upheld', 'human upheld the refusal')}>
                uphold refusal
              </Button>
              <Button tone="warn"
                      onClick={() => selected && api.decide(selected, 'overridden', 'human overrode the refusal')}>
                override
              </Button>
              <span className="text-[10.5px] text-faint">
                recorded in the same hash chain as the line's own decisions
              </span>
            </div>
          </Card>
        </div>
      </div>
    </Page>
  )
}
