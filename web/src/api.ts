import { useEffect, useRef, useState } from 'react'
import type { Bug, Brief, Finding, Integration, Overview, Patch, Repository, Scan, Trail, LineEvent } from './types'

const json = async <T,>(r: Response): Promise<T> => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}
const get = <T,>(p: string) => fetch(p).then(json<T>)
const post = <T,>(p: string, body: unknown = {}) =>
  fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' },
             body: JSON.stringify(body) }).then(json<T>)

export const api = {
  overview: () => get<Overview>('/api/overview'),
  repos: () => get<Repository[]>('/api/repos'),
  connectRepo: (b: { url?: string; path?: string; name?: string }) =>
    post<Repository & { error?: string }>('/api/repos', b),
  forgetRepo: (id: string) =>
    fetch(`/api/repos?id=${encodeURIComponent(id)}`, { method: 'DELETE' }).then(json),
  setAuto: (id: string, auto_scan: boolean) =>
    post<Repository>('/api/repo/auto', { id, auto_scan }),

  scans: () => get<Scan[]>('/api/scans'),
  scan: (id: string) => get<Scan>(`/api/scan?id=${encodeURIComponent(id)}`),
  startScan: (b: { repo_id: string; trigger?: string; runner?: string; enrich?: string }) =>
    post<{ scan_id?: string; error?: string }>('/api/scan', b),

  bugs: () => get<Bug[]>('/api/bugs'),
  findings: () => get<Record<string, Finding[]>>('/api/findings'),
  patch: (bug: string) => get<Patch>(`/api/patch?bug=${encodeURIComponent(bug)}`),
  trail: () => get<Trail>('/api/trail'),
  tamper: () => get<{ ok: boolean; why?: string; chain_ok?: boolean; problems?: string[] }>('/api/tamper'),

  integrations: () => get<Integration[]>('/api/integrations'),
  setSecret: (key: string, v: string, value: string) =>
    post<{ integrations: Integration[] }>('/api/integration', { key, var: v, value }),

  brief: (findings: Finding[]) => post<{ briefs: Brief[] }>('/api/brief', { findings }),
  decide: (bug_id: string, decision: string, note: string) =>
    post<{ seq: number; hash: string }>('/api/decision', { bug_id, decision, note }),
}

/** One shared SSE connection; components subscribe to it. */
const listeners = new Set<(e: LineEvent) => void>()
let source: EventSource | null = null

function ensureStream() {
  if (source) return
  source = new EventSource('/api/events')
  source.onmessage = (m) => {
    const event = JSON.parse(m.data) as LineEvent
    listeners.forEach((fn) => fn(event))
  }
}

export function useLineEvents(onEvent: (e: LineEvent) => void) {
  const ref = useRef(onEvent)
  ref.current = onEvent
  useEffect(() => {
    ensureStream()
    const fn = (e: LineEvent) => ref.current(e)
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  }, [])
}

/** Fetch on mount, and again whenever `deps` change or `reload()` is called. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    let live = true
    fnRef.current()
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e)))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, error, reload: () => setTick((t) => t + 1) }
}
