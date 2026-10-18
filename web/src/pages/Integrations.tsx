import { useState } from 'react'
import { api, useAsync } from '../api'
import { Badge, Button, Card } from '../ui'
import Page from './Page'

export default function Integrations() {
  const { data, reload } = useAsync(() => api.integrations(), [])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState('')

  const save = async (key: string, v: string) => {
    const id = `${key}.${v}`
    setSaving(id)
    try {
      await api.setSecret(key, v, draft[id] ?? '')
      setDraft((d) => ({ ...d, [id]: '' }))
      reload()
    } finally { setSaving('') }
  }

  return (
    <Page
      title="Integrations"
      sub="Credentials set here are live for the next scan. They are held in this process and in state/platform.json."
    >
      <div className="grid grid-cols-2 gap-3">
        {(data ?? []).map((i) => (
          <Card key={i.key} title={i.label}
                extra={<Badge kind={i.connected ? 'allow' : i.required ? 'escalate' : undefined}>
                  {i.connected ? 'connected' : i.required ? 'required' : 'optional'}
                </Badge>}>
            <p className="text-[11px] text-muted-fg">{i.role}</p>
            <div className="text-[10px] text-faint mt-1.5">
              {i.endpoint} · <a href={i.docs} target="_blank" rel="noreferrer"
                                className="text-verdict-info/85 hover:underline">docs</a>
            </div>

            <div className="mt-3 flex flex-col gap-2">
              {i.vars.map((v) => {
                const id = `${i.key}.${v.name}`
                return (
                  <div key={v.name} className="flex items-center gap-2">
                    <span className="w-40 shrink-0 text-[10.5px] text-muted-fg">{v.name}</span>
                    <input
                      type="password"
                      placeholder={v.set ? `${v.hint} (from ${v.source})` : 'not set'}
                      value={draft[id] ?? ''}
                      onChange={(e) => setDraft((d) => ({ ...d, [id]: e.target.value }))}
                      className="flex-1 bg-canvas border border-line-strong rounded-sm px-2.5 py-1.5
                                 text-[11px] outline-none focus:border-verdict-info
                                 placeholder:text-faint"
                    />
                    <Button onClick={() => save(i.key, v.name)}
                            disabled={!draft[id] || saving === id}>
                      {saving === id ? '…' : 'set'}
                    </Button>
                  </div>
                )
              })}
            </div>
          </Card>
        ))}
      </div>

      <Card title="how these are used" className="mt-3">
        <ul className="text-[11.5px] text-muted-fg leading-relaxed list-disc pl-4 space-y-1">
          <li><b className="text-body">Token Factory</b> runs every model call. Set
            <code className="text-amber-200/80"> MODEL_INSPECTOR</code> to a Nemotron id from the playground catalog.</li>
          <li><b className="text-body">Nemotron</b> is the semantic half of diff inspection —
            the step that needs judgement rather than pattern matching.</li>
          <li><b className="text-body">Sandboxes</b> gives the black box VM isolation and an
            outbound allowlist, which is the containment the brief calls the obvious next step.</li>
          <li><b className="text-body">Tavily</b> researches every escalation so the person it
            lands on arrives briefed, with sources.</li>
          <li><b className="text-body">n8n</b> orchestrates the line with an explicit error
            branch at each gate, so nothing fails silently.</li>
          <li><b className="text-body">Devin</b> is one black box implementation; sessions run
            in parallel, one per qualified bug.</li>
        </ul>
      </Card>
    </Page>
  )
}
