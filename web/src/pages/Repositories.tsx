import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, useAsync } from '../api'
import { Badge, Button, Card, Empty, Field, ago } from '../ui'
import Page from './Page'

export default function Repositories() {
  const { data, reload } = useAsync(() => api.repos(), [])
  const [url, setUrl] = useState('')
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const nav = useNavigate()

  const connect = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.connectRepo({ url, path })
      if ((r as { error?: string }).error) setError((r as { error?: string }).error!)
      else { setUrl(''); setPath(''); reload() }
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  const scan = async (id: string) => {
    await api.startScan({ repo_id: id, trigger: 'manual' })
    nav('/scan')
  }

  return (
    <Page title="Repositories" sub="Attach a checkout. Clones shallow; a local path is used as it is.">
      <div className="grid grid-cols-[1fr_420px] gap-3">
        <Card title="connected" pad={false}>
          {!data?.length ? <Empty>nothing connected yet</Empty> : data.map((r) => (
            <div key={r.id} className="border-t border-line first:border-0 px-4 py-3
                                       flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2.5">
                  <span className="text-[12.5px]">{r.name}</span>
                  <Badge kind={r.auto_scan ? 'allow' : undefined}>
                    {r.auto_scan ? 'auto scan on' : 'manual'}
                  </Badge>
                </div>
                <div className="text-[10px] text-faint mt-0.5 truncate">
                  {r.path} · {r.default_branch} · head {r.last_scanned_sha || '—'} ·
                  connected {ago(r.connected_at)}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Button onClick={async () => { await api.setAuto(r.id, !r.auto_scan); reload() }}>
                  {r.auto_scan ? 'disable auto' : 'enable auto'}
                </Button>
                <Button tone="go" onClick={() => scan(r.id)}>scan now</Button>
                <Button tone="warn" onClick={async () => { await api.forgetRepo(r.id); reload() }}>
                  forget
                </Button>
              </div>
            </div>
          ))}
        </Card>

        <div className="flex flex-col gap-3">
          <Card title="connect a repository">
            <div className="flex flex-col gap-3">
              <Field label="clone url" placeholder="https://github.com/owner/name.git"
                     value={url} onChange={(e) => setUrl(e.target.value)} />
              <Field label="or local path" placeholder="wp" value={path}
                     hint="Leave the url empty to attach a checkout already on disk."
                     onChange={(e) => setPath(e.target.value)} />
              {error && <div className="text-[11px] text-verdict-reject">{error}</div>}
              <Button tone="go" onClick={connect} disabled={busy || (!url && !path)}>
                {busy ? 'connecting…' : 'connect'}
              </Button>
            </div>
          </Card>

          <Card title="auto scan">
            <p className="text-[11px] text-muted-fg leading-relaxed">
              With auto scan on, the platform watches HEAD and starts a scan when it
              moves. Manual scans run the same line with the same interlocks — the
              trigger is recorded, nothing else changes.
            </p>
          </Card>
        </div>
      </div>
    </Page>
  )
}
