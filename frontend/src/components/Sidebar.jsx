import { NavLink } from 'react-router-dom'
import logo from '../assets/tradesight-logo.png'

const NAV = [
  { to: '/',          label: 'Dashboard' },
  { to: '/charts',    label: 'Charts' },
  { to: '/signals',   label: 'Signals' },
  { to: '/backtest',  label: 'Backtest' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/news',      label: 'News' },
  { to: '/tokens',    label: 'Usage' },
  { to: '/settings',  label: 'Settings' },
]

export default function Sidebar({ collapsed }) {
  return (
    <aside className={`flex flex-col bg-bg-secondary border-r border-bg-border transition-all duration-200 ${collapsed ? 'w-14' : 'w-48'} shrink-0`}>
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-bg-border h-14">
        <img src={logo} alt="TradeSight" className="h-6 w-auto invert" />
        {!collapsed && <span className="text-white text-xs font-semibold tracking-wide uppercase">TradeSight</span>}
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 space-y-0.5 px-2">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center px-3 py-2 rounded text-[13px] transition-colors ${
                isActive
                  ? 'bg-white/10 text-white font-medium'
                  : 'text-text-muted hover:bg-bg-hover hover:text-text-secondary'
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-bg-border">
        {!collapsed && <p className="text-[10px] text-text-muted tracking-wider uppercase">v0.5.0</p>}
      </div>
    </aside>
  )
}
