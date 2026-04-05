import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/',          icon: '⊞', label: 'Dashboard' },
  { to: '/charts',   icon: '📈', label: 'Charts' },
  { to: '/signals',  icon: '⚡', label: 'Signals' },
  { to: '/backtest', icon: '🔁', label: 'Backtest' },
  { to: '/portfolio',icon: '💼', label: 'Portfolio' },
  { to: '/news',     icon: '📰', label: 'News' },
  { to: '/tokens',   icon: '🪙', label: 'Token Usage' },
  { to: '/settings', icon: '⚙', label: 'Settings' },
]

export default function Sidebar({ collapsed }) {
  return (
    <aside className={`flex flex-col bg-bg-secondary border-r border-bg-border transition-all duration-200 ${collapsed ? 'w-14' : 'w-52'} shrink-0`}>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 py-4 border-b border-bg-border h-14">
        <span className="text-brand text-xl font-bold">TS</span>
        {!collapsed && <span className="text-text-primary font-semibold text-sm">TradeSight</span>}
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV.map(({ to, icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-2 py-2.5 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-brand/20 text-brand font-medium'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              }`
            }
          >
            <span className="text-base w-5 text-center shrink-0">{icon}</span>
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-bg-border">
        {!collapsed && <p className="text-xs text-text-muted">v0.4.0 Phase 4</p>}
      </div>
    </aside>
  )
}
