import { useState, useCallback } from 'react'
import { useApi } from '../hooks/useApi'
import { ENDPOINTS, apiFetch } from '../utils/api'
import MetricCard from '../components/MetricCard'
import { fmtUSD, fmtCurrency } from '../utils/formatters'

function CloseTradeBadge({ tradeId, onClosed }) {
  const [loading, setLoading] = useState(false)
  const [confirm, setConfirm] = useState(false)

  async function handleClose() {
    setLoading(true)
    try {
      await apiFetch(ENDPOINTS.closeTrade(tradeId), { method: 'POST' })
      setConfirm(false)
      if (onClosed) onClosed()
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }

  if (confirm) {
    return (
      <span className="flex gap-1">
        <button onClick={handleClose} disabled={loading} className="text-xs px-2 py-0.5 bg-short text-white rounded hover:bg-short/80">
          {loading ? '...' : 'Yes'}
        </button>
        <button onClick={() => setConfirm(false)} className="text-xs px-2 py-0.5 bg-bg-border text-text-muted rounded">No</button>
      </span>
    )
  }

  return (
    <button onClick={() => setConfirm(true)} className="text-xs px-2 py-0.5 bg-short/20 text-short rounded hover:bg-short/30 transition">
      Close
    </button>
  )
}

export default function Portfolio() {
  const { data: account, loading: accLoading, error: accError } = useApi(ENDPOINTS.accountSummary, { interval: 30000 })
  const { data: positions, loading: posLoading, refetch: refetchPositions } = useApi(ENDPOINTS.positions, { interval: 30000 })
  const { data: openTrades, loading: openLoading, refetch: refetchOpen } = useApi(ENDPOINTS.openTrades, { interval: 15000 })
  const { data: tradeHist } = useApi(ENDPOINTS.tradeHistory(50))

  const positionList = positions || []
  const openList = openTrades || []
  const historyList = tradeHist || []
  const pl = account?.unrealized_pl ?? null
  const plColor = pl == null ? undefined : pl >= 0 ? 'text-long' : 'text-short'

  const handleClosed = useCallback(() => {
    refetchPositions()
    refetchOpen()
  }, [refetchPositions, refetchOpen])

  // Equity curve from closed trades
  const equityData = historyList.filter(t => t.actual_pnl != null).reverse()
  let running = account?.balance ?? 100000
  const equityPoints = equityData.map(t => {
    running += t.actual_pnl
    return { date: t.closed_at?.slice(0, 10) || '', equity: running }
  })

  // Stats from history
  const totalTrades = historyList.length
  const wins = historyList.filter(t => t.actual_pnl > 0).length
  const winRate = totalTrades > 0 ? `${Math.round((wins / totalTrades) * 100)}%` : '—'
  const totalPnl = historyList.reduce((s, t) => s + (t.actual_pnl || 0), 0)

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Portfolio</h1>

      {accError && (
        <div className="bg-warn/10 border border-warn/30 text-warn text-sm px-4 py-3 rounded-md">
          Could not load OANDA account data: {accError}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard label="Balance" value={account ? fmtUSD(account.balance) : '—'} loading={accLoading} />
        <MetricCard label="Equity (NAV)" value={account ? fmtUSD(account.equity) : '—'} loading={accLoading} />
        <MetricCard label="Unrealized P&L" value={pl != null ? fmtCurrency(pl) : '—'} color={plColor} loading={accLoading} />
        <MetricCard label="Open Trades" value={account?.open_trade_count?.toString() ?? '—'} loading={accLoading} />
        <MetricCard label="Win Rate" value={winRate} sub={`${totalTrades} closed`} />
      </div>

      {/* Open Trades from OANDA */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Live Trades (OANDA)</h2>
        {openLoading ? (
          <div className="skeleton h-20" />
        ) : openList.length === 0 ? (
          <p className="text-text-muted text-sm">No open trades.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-bg-border text-left">
                  {['ID', 'Instrument', 'Side', 'Units', 'Entry', 'Current P&L', 'SL', 'TP', ''].map(h => (
                    <th key={h} className="label pb-2 pr-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {openList.map(t => {
                  const pl = parseFloat(t.unrealizedPL || t.unrealized_pl || 0)
                  const isLong = parseFloat(t.currentUnits || t.units || 0) > 0
                  return (
                    <tr key={t.id} className="border-b border-bg-border/50">
                      <td className="py-2 pr-3 font-mono text-xs text-text-muted">{t.id}</td>
                      <td className="py-2 pr-3 font-medium">{t.instrument?.replace('_', '/')}</td>
                      <td className="py-2 pr-3">
                        <span className={isLong ? 'badge-long' : 'badge-short'}>{isLong ? 'LONG' : 'SHORT'}</span>
                      </td>
                      <td className="py-2 pr-3 font-mono">{Math.abs(parseFloat(t.currentUnits || t.units || 0))}</td>
                      <td className="py-2 pr-3 font-mono">{parseFloat(t.price || 0).toFixed(5)}</td>
                      <td className={`py-2 pr-3 font-mono ${pl >= 0 ? 'text-long' : 'text-short'}`}>
                        {fmtCurrency(pl)}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {t.stopLossOrder?.price || t.stop_loss || '—'}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {t.takeProfitOrder?.price || t.take_profit || '—'}
                      </td>
                      <td className="py-2">
                        <CloseTradeBadge tradeId={t.id} onClosed={handleClosed} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Margin info */}
        <div className="card">
          <h2 className="font-medium text-text-primary mb-1">Margin</h2>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Margin Used</span>
              <span className="font-mono">{account ? fmtUSD(account.margin_used) : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Margin Available</span>
              <span className="font-mono text-long">{account ? fmtUSD(account.margin_available) : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Total P&L (closed)</span>
              <span className={`font-mono ${totalPnl >= 0 ? 'text-long' : 'text-short'}`}>{fmtCurrency(totalPnl)}</span>
            </div>
          </div>
        </div>

        {/* Equity Curve (simple bar) */}
        <div className="card">
          <h2 className="font-medium text-text-primary mb-3">Equity Curve</h2>
          {equityPoints.length === 0 ? (
            <p className="text-text-muted text-sm">No closed trades yet.</p>
          ) : (
            <div className="flex items-end gap-0.5 h-32">
              {equityPoints.map((pt, i) => {
                const min = Math.min(...equityPoints.map(p => p.equity))
                const max = Math.max(...equityPoints.map(p => p.equity))
                const range = max - min || 1
                const heightPct = ((pt.equity - min) / range) * 80 + 20
                const isUp = i === 0 || pt.equity >= equityPoints[i - 1].equity
                return (
                  <div
                    key={i}
                    className={`flex-1 rounded-t ${isUp ? 'bg-long/70' : 'bg-short/70'}`}
                    style={{ height: `${heightPct}%` }}
                    title={`${pt.date}: ${fmtUSD(pt.equity)}`}
                  />
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Trade History */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Trade History</h2>
        {historyList.length === 0 ? (
          <p className="text-text-muted text-sm">No closed trades yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-bg-border text-left">
                  {['Instrument', 'Side', 'Entry', 'Exit', 'P&L', 'Exit Reason', 'Closed'].map(h => (
                    <th key={h} className="label pb-2 pr-3">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {historyList.map(t => (
                  <tr key={t.id} className="border-b border-bg-border/50">
                    <td className="py-2 pr-3 font-medium">{t.instrument?.replace('_', '/')}</td>
                    <td className="py-2 pr-3">
                      <span className={t.direction === 'long' ? 'badge-long' : 'badge-short'}>
                        {t.direction?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono">{t.entry_price?.toFixed(5) ?? '—'}</td>
                    <td className="py-2 pr-3 font-mono">{t.actual_exit_price?.toFixed(5) ?? '—'}</td>
                    <td className={`py-2 pr-3 font-mono ${(t.actual_pnl || 0) >= 0 ? 'text-long' : 'text-short'}`}>
                      {t.actual_pnl != null ? fmtCurrency(t.actual_pnl) : '—'}
                    </td>
                    <td className="py-2 pr-3 text-xs text-text-muted">{t.exit_reason?.replace('_', ' ') ?? '—'}</td>
                    <td className="py-2 pr-3 text-xs text-text-muted">{t.closed_at?.slice(0, 16)?.replace('T', ' ') ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
