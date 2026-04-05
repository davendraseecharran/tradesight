import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import { fmtDate } from '../utils/formatters'

const IMPACT_COLOR = {
  high: 'text-short bg-short/10 border-short/30',
  medium: 'text-warn bg-warn/10 border-warn/30',
  low: 'text-text-muted bg-bg-hover border-bg-border',
}

export default function NewsCalendar({ limit = 5, hours = 48 }) {
  const { data, loading } = useApi(ENDPOINTS.newsCalendar(hours))
  const events = (data || []).slice(0, limit)

  if (loading) return (
    <div className="space-y-2">
      {Array(3).fill(0).map((_, i) => <div key={i} className="skeleton h-12" />)}
    </div>
  )

  if (!events.length) return (
    <p className="text-text-muted text-sm">No upcoming events in next {hours}h</p>
  )

  return (
    <div className="space-y-2">
      {events.map(ev => (
        <div key={ev.id} className={`flex items-center gap-3 px-3 py-2 rounded-md border text-sm ${IMPACT_COLOR[ev.impact] ?? IMPACT_COLOR.low}`}>
          <span className="font-mono font-semibold w-8 shrink-0">{ev.currency}</span>
          <div className="flex-1 min-w-0">
            <p className="truncate font-medium">{ev.event}</p>
            <p className="text-xs opacity-70">{fmtDate(ev.event_datetime)}</p>
          </div>
          <span className="text-xs uppercase font-semibold shrink-0">{ev.impact}</span>
        </div>
      ))}
    </div>
  )
}
