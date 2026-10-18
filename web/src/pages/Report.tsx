import { useParams, useNavigate } from 'react-router-dom'
import { api, useAsync } from '../api'
import { Badge, Button, Card, Empty, Meter, Stat, VERDICT_BG, ago } from '../ui'
import { SEV_ORDER } from '../ui'
import Page from './Page'

const seconds = (s: { started_at: number; finished_at: number | null }) =>
  Math.max(0, Math.round((s.finished_at ?? Date.now() / 1000) - s.started_at))

export default function Report() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: scans } = useAsync(() => api.scans(), [])
  const { data: trail } = useAsync(() => api.trail(), [id])

  const scan = id ? scans?.find((s) => s.id === id) : scans?.[0]

  if (!scans?.length) return <Page title="Reports"><Card><Empty>no scans yet</Empty></Card></Page>
  if (!scan) return <Page title="Reports"><Card><Empty>unknown scan</Empty></Card></Page>

  const bySeverity = SEV_ORDER.map((s) => ({
    severity: s, count: scan.findings.filter((f) => f.severity === s).length,
  })).filter((r) => r.count)

  const entries = trail?.entries.filter((e) => scan.bugs.includes(e.bug_id)) ?? []

  return (
    <Page
      title={`Report · ${scan.id}`}
      sub={`${scan.trigger} scan · runner ${scan.runner} · ${ago(scan.started_at)} · ${seconds(scan)}s`}
      actions={
        <select value={scan.id} onChange={(e) => nav(`/reports/${e.target.value}`)}
                className="bg-sunken border border-line-strong rounded-sm px-2 py-1.5 text-[11px]">
          {scans.map((s) => <option key={s.id} value={s.id}>{s.id} · {ago(s.started_at)}</option>)}
        </select>
      }
    >
      <div className="grid grid-cols-4 gap-3">
        <Stat label="shipped unattended" value={scan.shipped} tone="text-verdict-allow" />
        <Stat label="refused" value={scan.refused} tone="text-verdict-reject" />
        <Stat label="escalated" value={scan.escalated} tone="text-verdict-escalate" />
        <Stat label="audit chain" value={scan.chain_ok ? 'intact' : 'broken'}
              tone={scan.chain_ok ? 'text-verdict-allow' : 'text-verdict-reject'} />
      </div>

      <div className="grid grid-cols-[1fr_320px] gap-3 mt-3">
        <Card title="decision trail" pad={false}>
          {entries.length === 0 ? <Empty>no entries</Empty> : (
            <table className="w-full text-[11.5px]">
              <tbody>
                {entries.map((e) => (
                  <tr key={e.seq} className="border-t border-line first:border-0">
                    <td className="px-4 py-2 text-faint tabular-nums mono w-12">#{e.seq}</td>
                    <td className="text-muted-fg mono w-28">{e.bug_id}</td>
                    <td className="w-24">{e.stage}</td>
                    <td className="w-24"><Badge kind={e.decision}>{e.decision}</Badge></td>
                    <td className="text-muted-fg pr-4 truncate">{e.summary}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="flex flex-col gap-3">
          <Card title="findings by severity">
            {bySeverity.length === 0 ? <Empty>none raised</Empty> : bySeverity.map((r) => (
              <div key={r.severity} className="flex items-center gap-3 py-1">
                <span className="w-16 text-[10.5px] text-muted-fg">{r.severity}</span>
                <Meter value={r.count} max={Math.max(...bySeverity.map((x) => x.count))}
                       tone={r.severity === 'critical' ? 'bg-verdict-reject'
                         : r.severity === 'high' ? 'bg-verdict-escalate' : 'bg-line-strong'} />
                <span className="tabular-nums text-[11px] w-5 text-right">{r.count}</span>
              </div>
            ))}
          </Card>

          <Card title="bugs in this scan">
            {scan.bugs.map((b) => <div key={b} className="text-[11.5px] py-0.5">{b}</div>)}
          </Card>

          <Card title="chain">
            <div className="flex flex-wrap gap-[3px]">
              {entries.map((e) => (
                <i key={e.seq} title={`${e.stage} · ${e.summary}`}
                   className={`w-2.5 h-2.5 rounded-[2px] ${VERDICT_BG[e.decision] ?? 'bg-line-strong'}`} />
              ))}
            </div>
            <Button className="mt-3 w-full" onClick={() => window.print()}>export</Button>
          </Card>
        </div>
      </div>
    </Page>
  )
}
