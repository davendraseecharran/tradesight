import { useState } from 'react'
import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import SignalCard from '../components/SignalCard'
import TradeHistory from '../components/TradeHistory'

export default function Signals() {
  const [tab, setTab] = useState('active')
  const { data: active, loading: activeLoading, refetch } = useApi(ENDPOINTS.activeSignals, { interval: 30000 })
  const { data: history, loading: histLoading } = useApi(ENDPOINTS.signalHistory(100))

  const activeSignals = active || []
  const histSignals = history || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Signals</h1>
        <button onClick={refetch} className="btn-secondary text-xs">Refresh</button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-bg-border gap-4">
        {[['active', `Active (${activeSignals.length})`], ['history', `History (${histSignals.length})`]].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
              tab === key ? 'border-white text-white' : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'active' && (
        <div>
          {activeLoading ? (
            <div className="space-y-3">{Array(2).fill(0).map((_, i) => <div key={i} className="skeleton h-40" />)}</div>
          ) : activeSignals.length === 0 ? (
            <div className="card text-center py-16 text-text-muted">
              <p className="font-medium">No active signals</p>
              <p className="text-sm mt-1">The screener runs every 4H. Use Charts &rarr; Analyze to trigger manually.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
              {activeSignals.map(s => <SignalCard key={s.id} signal={s} />)}
            </div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="card">
          {histLoading ? (
            <div className="skeleton h-48" />
          ) : (
            <TradeHistory signals={histSignals} />
          )}
        </div>
      )}
    </div>
  )
}
