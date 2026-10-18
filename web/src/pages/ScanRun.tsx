import { useRef, useState } from 'react'
import { api, useAsync, useLineEvents } from '../api'
import Pipeline, { STAGES } from '../Pipeline'
import { Badge, Button, Card, Empty, VERDICT } from '../ui'
import type { LineEvent } from '../types'
import Page from './Page'

interface Row { text: string; kind: string }

export default function ScanRun() {
  const { data: overview, reload } = useAsync(() => api.overview(), [])
  const [stages, setStages] = useState<Record<string, string>>({})
  const [bug, setBug] = useState<{ id: string; title: string; source: string } | null>(null)
  const [verdict, setVerdict] = useState<{ decision: string; reason: string } | null>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [stoppedAt, setStoppedAt] = useState<string | null>(null)
  const [rows, setRows] = useState<Row[]>([])
  const [running, setRunning] = useState(false)

  // Events arrive faster than they can be read, so each one is held on
  // screen for a beat before the next is applied.
  const pending = useRef<LineEvent[]>([])
  const draining = useRef(false)

  const log = (text: string, kind = '') =>
    setRows((r) => [...r.slice(-120), { text, kind }])

  const beat = (ms: number) => new Promise((r) => setTimeout(r, ms))

  async function apply(e: LineEvent) {
    switch (e.kind) {
      case 'scan_start':
        setStages({}); setVerdict(null); setOutcome(null); setStoppedAt(null)
        setRows([]); setRunning(true)
        log(`scan ${e.scan_id} · ${e.repo} · ${e.trigger} · runner=${e.runner}`, 'researched')
        break
      case 'auto_trigger':
        log(`head moved ${e.from} → ${e.to} on ${e.repo}`, 'researched')
        break
      case 'intake':
        setStages({}); setVerdict(null); setOutcome(null); setStoppedAt(null)
        setBug({ id: String(e.bug_id), title: String(e.title ?? ''), source: String(e.source ?? '') })
        log(`intake ${e.bug_id}`)
        await beat(500)
        break
      case 'stage_start':
        setStages((s) => ({ ...s, [String(e.stage)]: 'run' }))
        await beat(560)
        break
      case 'stage_done':
        setStages((s) => ({ ...s, [String(e.stage)]: String(e.decision) }))
        log(`${String(e.stage).padEnd(11)}${String(e.decision).padEnd(10)}${e.reason}`,
            String(e.decision))
        await beat(420)
        break
      case 'outcome':
        setVerdict({ decision: String(e.decision), reason: String(e.reason ?? '') })
        setOutcome(String(e.decision))
        setStoppedAt(e.stopped_at ? String(e.stopped_at) : null)
        await beat(1400)
        break
      case 'scan_done':
        setRunning(false)
        log(`scan complete — ${e.shipped} shipped, ${e.refused} refused, ` +
            `${e.escalated} escalated, chain ${e.chain_ok ? 'intact' : 'BROKEN'}`,
            e.chain_ok ? 'allow' : 'reject')
        reload()
        break
      case 'scan_failed':
        setRunning(false)
        log(`scan failed: ${e.message}`, 'reject')
        break
    }
  }

  useLineEvents((e) => {
    pending.current.push(e)
    if (draining.current) return
    draining.current = true
    ;(async () => {
      while (pending.current.length) {
        const next = pending.current.shift()!
        try { await apply(next) } catch (err) { console.error(next.kind, err) }
      }
      draining.current = false
    })()
  })

  const start = async () => {
    const repo = overview?.repos[0]
    if (!repo) return
    await api.startScan({ repo_id: repo.id, trigger: 'manual' })
  }

  const done = STAGES.filter((s) => stages[s] && stages[s] !== 'run').length

  return (
    <Page
      title="Live scan"
      sub="Driven by the server's event stream — every light is a decision the line took."
      actions={
        <>
          <Button onClick={async () => {
            const r = await api.tamper()
            log(r.ok ? (r.problems?.[0] ?? 'chain broken') : (r.why ?? ''), 'reject')
          }}>tamper with audit</Button>
          <Button tone="go" onClick={start} disabled={running || !overview?.repos.length}>
            {running ? 'running' : 'run scan'}
          </Button>
        </>
      }
    >
      {!overview?.repos.length && (
        <div className="mb-3"><Badge kind="escalate">connect a repository first</Badge></div>
      )}

      <Card pad={false}>
        <Pipeline
          stages={stages}
          outcome={outcome}
          stoppedAt={stoppedAt}
          verdict={verdict}
          title={bug?.title ?? 'idle'}
          subtitle={bug
            ? <><span className="mono text-head">{bug.id}</span> · {bug.source}</>
            : 'press run scan to put a bug on the line'}
        />
      </Card>

      <Card
        title="log"
        pad={false}
        className="mt-3"
        extra={<span className="text-[10.5px] text-faint">{done}/{STAGES.length} gates settled</span>}
      >
        <div className="h-[240px] overflow-y-auto px-4 py-2.5 mono text-[11.5px] leading-[1.8]">
          {rows.length === 0 ? <Empty>nothing yet</Empty> : rows.map((r, i) => (
            <div key={i} className={`whitespace-pre truncate ${VERDICT[r.kind] ?? 'text-muted-fg'}`}>
              {r.text}
            </div>
          ))}
        </div>
      </Card>
    </Page>
  )
}
