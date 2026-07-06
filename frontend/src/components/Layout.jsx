import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'

function StatusDot({ ok }) {
  return (
    <span className={`inline-block w-1.5 h-1.5 rounded-full ${ok ? 'bg-long' : 'bg-short'}`} />
  )
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const { data: health } = useApi(ENDPOINTS.health, { interval: 30000 })
  const { data: schedule } = useApi(ENDPOINTS.signalSchedule, { interval: 60000 })

  const marketOpen = schedule?.is_open ?? false
  // Per-connection status from /health. Fall back to overall status for
  // older backends that don't report connections yet.
  const oandaOk = health?.connections?.oanda ?? (health?.status === 'ok')
  const claudeOk = health?.connections?.claude ?? (health?.status === 'ok')
  const problems = health?.problems ?? []

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar collapsed={collapsed} />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="flex items-center justify-between px-4 h-12 bg-bg-secondary border-b border-bg-border shrink-0">
          <button
            onClick={() => setCollapsed(c => !c)}
            className="text-text-muted hover:text-text-primary transition-colors p-1 text-sm"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 4h12M2 8h12M2 12h12" />
            </svg>
          </button>

          <div className="flex items-center gap-5 text-[11px] text-text-muted font-medium tracking-wide">
            {/* Market status */}
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${marketOpen ? 'bg-long' : 'bg-neutral-600'}`} />
              <span className={marketOpen ? 'text-text-secondary' : ''}>
                {marketOpen ? 'MARKET OPEN' : 'MARKET CLOSED'}
              </span>
            </span>

            {/* Time */}
            {schedule?.current_time_et && (
              <span className="font-mono text-text-muted">{schedule.current_time_et}</span>
            )}

            {/* Separator */}
            <span className="w-px h-3 bg-bg-border" />

            {/* System health (hover for details) */}
            {problems.length > 0 && (
              <span
                className="flex items-center gap-1.5 text-amber-500 cursor-help"
                title={problems.join('\n')}
              >
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500" />
                <span>{problems.length} ISSUE{problems.length > 1 ? 'S' : ''}</span>
              </span>
            )}

            {/* OANDA status */}
            <span className="flex items-center gap-1.5">
              <StatusDot ok={oandaOk} />
              <span>OANDA</span>
            </span>

            {/* Claude status */}
            <span className="flex items-center gap-1.5">
              <StatusDot ok={claudeOk} />
              <span>CLAUDE</span>
            </span>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
