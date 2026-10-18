export type Decision = 'allow' | 'reject' | 'escalate' | 'produced' | 'accepted' | 'researched'
export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export interface Repository {
  id: string; name: string; url: string; path: string
  provider: string; default_branch: string; connected_at: number
  auto_scan: boolean; last_scanned_sha: string; last_scan_id: string
}

export interface Scan {
  id: string; repo_id: string; trigger: 'manual' | 'auto' | 'webhook'
  started_at: number; finished_at: number | null
  status: 'running' | 'done' | 'failed'
  shipped: number; refused: number; escalated: number
  bugs: string[]; findings: Finding[]; chain_ok: boolean
  runner: string; note: string
}

export interface Finding {
  rule: string; severity: Severity; file: string; line: number
  evidence: string; rationale: string; layer: string
  /** Weakness class, e.g. CWE-79, with its common name. */
  cwe?: string; name?: string
  bug_id?: string; bug_title?: string
}

export interface Bug {
  id: string; title: string; source: string; body: string
  file: string; has_patch: boolean
  seed?: { sha?: string; red_tests?: string[]; selectors?: string[] }
}

export interface IntegrationVar {
  name: string; set: boolean; source: string; hint: string
}

export interface Integration {
  key: string; label: string; role: string; endpoint: string; docs: string
  required: boolean; connected: boolean; vars: IntegrationVar[]
}

export interface AuditEntry {
  seq: number; ts: number; bug_id: string; stage: string
  decision: string; summary: string; payload: Record<string, unknown>
  prev_hash: string; entry_hash: string; signature: string
}

export interface Trail { entries: AuditEntry[]; chain_ok: boolean; problems: string[] }

export interface Patch { proposed?: string; reference?: string; regression?: string }

export interface Overview {
  repos: Repository[]; scans: Scan[]; running: string | null
  bugs: number; integrations: Integration[]; policy: string
  defaults: { runner: string; judge: string; enrich: string }
}

export interface Brief {
  rule: string; query: string; answer: string
  sources: { title: string; url: string; snippet: string; score: number }[]
  error: string | null
}

/** Anything the pipeline pushes down the event stream. */
export interface LineEvent {
  kind: string; ts: number; scan_id?: string; bug_id?: string
  stage?: string; decision?: string; reason?: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detail?: any
  [k: string]: unknown
}
