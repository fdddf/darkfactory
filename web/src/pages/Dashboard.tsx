import { Link, useNavigate } from 'react-router-dom'
import { api, useAsync, useLineEvents } from '../api'
import { Badge, Button, Card, Dot, Empty, Stat, ago } from '../ui'
import Page from './Page'

export default function Dashboard() {
  const { data, reload } = useAsync(() => api.overview(), [])
  const nav = useNavigate()
  useLineEvents((e) => { if (e.kind === 'scan_done') reload() })

  const scans = data?.scans ?? []
  const last = scans[0]
  const shipped = scans.reduce((n, s) => n + s.shipped, 0)
  const refused = scans.reduce((n, s) => n + s.refused, 0)
  const escalated = scans.reduce((n, s) => n + s.escalated, 0)

  const run = async () => {
    const repo = data?.repos[0]
    if (!repo) return nav('/repositories')
    await api.startScan({ repo_id: repo.id, trigger: 'manual' })
    nav('/scan')
  }

  return (
    <Page
      title="Overview"
      sub="A fix ships only when every interlock clears. Everything else goes to a person."
      actions={<Button tone="go" onClick={run} disabled={!!data?.running}>
        {data?.running ? 'scan running' : 'run scan'}
      </Button>}
    >
      <div className="grid grid-cols-4 gap-3">
        <Stat label="shipped unattended" value={shipped} tone="text-verdict-allow" />
        <Stat label="refused" value={refused} tone="text-verdict-reject" />
        <Stat label="escalated" value={escalated} tone="text-verdict-escalate" />
        <Stat label="seeded bugs" value={data?.bugs ?? '—'} />
      </div>

      <div className="grid grid-cols-[1.4fr_1fr] gap-3 mt-3">
        <Card title="recent scans" extra={<Link to="/reports" className="text-[10px] text-faint hover:text-head">all reports</Link>} pad={false}>
          {scans.length === 0 ? <Empty>no scans yet — run one</Empty> : (
            <table className="w-full text-[11.5px]">
              <thead>
                <tr className="text-faint text-[9.5px] tracking-[0.16em] uppercase">
                  <th className="text-left font-medium px-4 py-2">scan</th>
                  <th className="text-left font-medium">trigger</th>
                  <th className="text-right font-medium">ship</th>
                  <th className="text-right font-medium">refuse</th>
                  <th className="text-right font-medium">escalate</th>
                  <th className="text-right font-medium px-4">when</th>
                </tr>
              </thead>
              <tbody>
                {scans.map((s) => (
                  <tr key={s.id} className="border-t border-line hover:bg-sunken cursor-pointer transition"
                      onClick={() => nav(`/reports/${s.id}`)}>
                    <td className="px-4 py-2.5 mono font-medium">{s.id}</td>
                    <td className="text-muted-fg">{s.trigger}</td>
                    <td className="text-right text-verdict-allow tabular-nums">{s.shipped}</td>
                    <td className="text-right text-verdict-reject tabular-nums">{s.refused}</td>
                    <td className="text-right text-verdict-escalate tabular-nums">{s.escalated}</td>
                    <td className="text-right px-4 text-faint">{ago(s.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <div className="flex flex-col gap-3">
          <Card title="repositories">
            {(data?.repos ?? []).map((r) => (
              <div key={r.id} className="flex items-center justify-between py-1.5">
                <div>
                  <div className="text-[12px]">{r.name}</div>
                  <div className="text-[10.5px] text-faint mono">
                    {r.default_branch} · {r.last_scanned_sha || 'never scanned'}
                  </div>
                </div>
                <Badge kind={r.auto_scan ? 'allow' : undefined}>
                  {r.auto_scan ? 'auto' : 'manual'}
                </Badge>
              </div>
            ))}
            {!data?.repos.length && <Empty>connect a repository</Empty>}
          </Card>

          <Card title="services">
            <div className="grid grid-cols-2 gap-y-1.5">
              {(data?.integrations ?? []).map((i) => (
                <div key={i.key} className="flex items-center gap-2 text-[11.5px]">
                  <Dot kind={i.connected ? 'allow' : undefined} />
                  <span className={i.connected ? 'text-body' : 'text-faint'}>{i.label}</span>
                </div>
              ))}
            </div>
          </Card>

          {last && (
            <Card title="audit chain">
              <Badge kind={last.chain_ok ? 'allow' : 'reject'}>
                {last.chain_ok ? 'intact' : 'broken'}
              </Badge>
              <p className="text-[10.5px] text-faint mt-2 leading-relaxed">
                Every decision commits to the hash of the one before it. Edit one
                byte and the chain names the entry.
              </p>
            </Card>
          )}
        </div>
      </div>
    </Page>
  )
}
