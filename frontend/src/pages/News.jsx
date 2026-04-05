import { useState } from 'react'
import { useApi, usePost } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import { fmtDate } from '../utils/formatters'

const IMPACT_STYLE = {
  high:   'border-short/40 bg-short/5 text-short',
  medium: 'border-warn/40 bg-warn/5 text-warn',
  low:    'border-bg-border bg-bg-hover text-text-muted',
}

const IMPACT_TABS = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
]

export default function News() {
  const { data, loading, refetch } = useApi(ENDPOINTS.newsCalendar(168), { interval: 300000 })
  const { post: refresh, loading: refreshing } = usePost(ENDPOINTS.refreshNews)
  const [impactFilter, setImpactFilter] = useState('all')
  const events = data || []

  const now = new Date()
  const active = events.filter(e => {
    const start = new Date(e.blackout_start)
    const end = new Date(e.blackout_end)
    return now >= start && now <= end && e.impact === 'high'
  })

  const filtered = impactFilter === 'all'
    ? events
    : events.filter(e => e.impact === impactFilter)

  const counts = {
    all: events.length,
    high: events.filter(e => e.impact === 'high').length,
    medium: events.filter(e => e.impact === 'medium').length,
    low: events.filter(e => e.impact === 'low').length,
  }

  const [msg, setMsg] = useState(null)

  const handleRefresh = async () => {
    setMsg(null)
    const { data, error } = await refresh()
    if (error) {
      setMsg({ type: 'error', text: error })
    } else if (data?.status === 'error') {
      setMsg({ type: 'error', text: data.error || 'Unknown error' })
    } else if (data) {
      setMsg({ type: 'success', text: `Fetched ${data.raw_events_fetched} events, stored ${data.events_stored}` })
    }
    refetch()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Economic Calendar</h1>
        <button onClick={handleRefresh} disabled={refreshing} className="btn-secondary text-xs">
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {msg && (
        <div className={`px-4 py-3 rounded-md text-sm border ${
          msg.type === 'success' ? 'bg-long/10 border-long/30 text-long' :
                                   'bg-short/10 border-short/30 text-short'
        }`}>
          {msg.text}
        </div>
      )}

      {active.length > 0 && (
        <div className="bg-short/10 border border-short/30 rounded-lg px-4 py-3">
          <p className="text-short font-semibold text-sm mb-2">Active Blackout Windows</p>
          {active.map(e => (
            <p key={e.id} className="text-short text-sm">
              [{e.currency}] {e.event} — until {fmtDate(e.blackout_end)}
            </p>
          ))}
        </div>
      )}

      {/* Impact filter tabs */}
      <div className="flex border-b border-bg-border gap-4">
        {IMPACT_TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setImpactFilter(key)}
            className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
              impactFilter === key ? 'border-white text-white' : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            {label} ({counts[key]})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-2">{Array(6).fill(0).map((_, i) => <div key={i} className="skeleton h-16" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="card text-center py-16 text-text-muted">
          <p className="text-text-secondary">
            {events.length === 0
              ? 'No events loaded. Click Refresh to fetch from ForexFactory.'
              : `No ${impactFilter} impact events found.`}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(ev => {
            const isActive = ev.impact === 'high' && now >= new Date(ev.blackout_start) && now <= new Date(ev.blackout_end)
            return (
              <div key={ev.id} className={`flex items-center gap-4 px-4 py-3 rounded-lg border text-sm ${IMPACT_STYLE[ev.impact] ?? IMPACT_STYLE.low} ${isActive ? 'ring-1 ring-short' : ''}`}>
                <div className="w-16 shrink-0">
                  <span className="text-xs uppercase font-bold">{ev.impact}</span>
                </div>
                <div className="w-12 shrink-0 font-mono font-semibold">{ev.currency}</div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-text-primary truncate">{ev.event}</p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {fmtDate(ev.event_datetime)}
                    {ev.impact === 'high' && <> · Blackout {fmtDate(ev.blackout_start)} – {fmtDate(ev.blackout_end)}</>}
                  </p>
                </div>
                {isActive && <span className="text-xs bg-short text-white px-2 py-0.5 rounded shrink-0">ACTIVE</span>}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
