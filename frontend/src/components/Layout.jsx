import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const { data: health } = useApi(ENDPOINTS.health, { interval: 30000 })
  const { data: schedule } = useApi(ENDPOINTS.signalSchedule, { interval: 60000 })

  const marketOpen = schedule?.is_open ?? false

  return (
    <div className="flex h-screen overflow-hidden bg-bg-primary">
      <Sidebar collapsed={collapsed} />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="flex items-center justify-between px-4 h-14 bg-bg-secondary border-b border-bg-border shrink-0">
          <button
            onClick={() => setCollapsed(c => !c)}
            className="text-text-muted hover:text-text-primary transition-colors p-1"
          >
            ☰
          </button>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            <span className={`flex items-center gap-1.5 ${marketOpen ? 'text-long' : 'text-short'}`}>
              <span className={`w-2 h-2 rounded-full ${marketOpen ? 'bg-long animate-pulse' : 'bg-short'}`} />
              Market {marketOpen ? 'Open' : 'Closed'}
            </span>
            {schedule?.current_time_et && (
              <span>{schedule.current_time_et}</span>
            )}
            <span className={health?.status === 'ok' ? 'text-long' : 'text-short'}>
              API {health?.status === 'ok' ? '●' : '○'}
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
