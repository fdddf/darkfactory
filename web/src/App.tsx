import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, useAsync, useLineEvents } from './api'
import { useState } from 'react'
import Dashboard from './pages/Dashboard'
import Repositories from './pages/Repositories'
import ScanRun from './pages/ScanRun'
import Findings from './pages/Findings'
import Report from './pages/Report'
import Integrations from './pages/Integrations'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/repositories', label: 'Repositories' },
  { to: '/scan', label: 'Live scan' },
  { to: '/findings', label: 'Findings' },
  { to: '/reports', label: 'Reports' },
  { to: '/integrations', label: 'Integrations' },
]

export default function App() {
  const { data: overview, reload } = useAsync(() => api.overview(), [])
  const [live, setLive] = useState<string | null>(null)

  useLineEvents((e) => {
    if (e.kind === 'scan_start') setLive(String(e.scan_id ?? ''))
    if (e.kind === 'scan_done' || e.kind === 'scan_failed') { setLive(null); reload() }
  })

  const connected = overview?.integrations.filter((i) => i.connected).length ?? 0
  const total = overview?.integrations.length ?? 0

  return (
    <div className="h-full grid grid-cols-[208px_1fr]">
      <aside className="border-r border-line bg-surface flex flex-col">
        <div className="h-14 px-4 flex items-center gap-2.5 border-b border-line">
          <span className="w-7 h-7 rounded-md bg-head text-white grid place-items-center
                           text-[13px] font-bold shrink-0">DF</span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold tracking-tight leading-tight">Dark Factory</div>
            <div className="text-[9px] uppercase tracking-[0.14em] text-faint truncate">
              autonomous bug resolution
            </div>
          </div>
        </div>

        <nav className="p-2 flex flex-col gap-0.5">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `px-3 py-2 rounded-md text-[12.5px] transition flex items-center ${
                  isActive
                    ? 'bg-wash-info text-verdict-info font-semibold'
                    : 'text-body hover:text-head hover:bg-sunken'
                }`
              }
            >
              {n.label}
              {n.to === '/scan' && live && (
                <i className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-verdict-info animate-pulse" />
              )}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto p-4 border-t border-line space-y-1.5">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-muted-fg">repositories</span>
            <span className="mono text-head">{overview?.repos.length ?? 0}</span>
          </div>
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-muted-fg">services</span>
            <span className="mono text-head">{connected}/{total}</span>
          </div>
          <p className="text-[10px] text-faint leading-relaxed pt-1.5">{overview?.policy ?? ''}</p>
        </div>
      </aside>

      <main className="overflow-y-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/scan" element={<ScanRun />} />
          <Route path="/findings" element={<Findings />} />
          <Route path="/reports" element={<Report />} />
          <Route path="/reports/:id" element={<Report />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
