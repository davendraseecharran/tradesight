import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import MetricCard from '../components/MetricCard'
import ErrorBoundary from '../components/ErrorBoundary'
import ChartWidget from '../components/ChartWidget'
import SignalCard from '../components/SignalCard'
import NewsCalendar from '../components/NewsCalendar'
import PairSelector from '../components/PairSelector'
import TimeframeSelector from '../components/TimeframeSelector'
import { fmtUSD, fmtCurrency } from '../utils/formatters'

export default function Dashboard() {
  const [pair, setPair] = useState('EUR_USD')
  const [timeframe, setTimeframe] = useState('4H')

  const { data: account, loading: accountLoading } = useApi(ENDPOINTS.accountSummary, { interval: 60000 })
  const { data: signals, loading: signalsLoading, refetch: refetchSignals } = useApi(ENDPOINTS.activeSignals, { interval: 60000 })
  const { data: openTrades, loading: tradesLoading } = useApi(ENDPOINTS.openTrades, { interval: 30000 })
  const { data: tradeHist } = useApi(ENDPOINTS.tradeHistory(50))

  const activeSignals = signals || []
  const approvedSignals = activeSignals.filter(s => s.risk_approved)
  const openTradeCount = openTrades?.length ?? account?.open_trade_count ?? 0

  // Win rate from trade history
  const historyList = tradeHist || []
  const totalClosed = historyList.length
  const wins = historyList.filter(t => t.actual_pnl > 0).length
  const winRate = totalClosed > 0 ? `${Math.round((wins / totalClosed) * 100)}%` : '—'

  const unrealizedPL = account?.unrealized_pl ?? null
  const plColor = unrealizedPL == null ? undefined : unrealizedPL >= 0 ? 'text-long' : 'text-short'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text-primary">Dashboard</h1>
        <Link to="/signals" className="text-xs text-text-secondary hover:text-white hover:underline">View all signals →</Link>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard
          label="Account Balance"
          value={account ? fmtUSD(account.balance) : '—'}
          sub={account?.currency ?? ''}
          loading={accountLoading}
        />
        <MetricCard
          label="Unrealized P&L"
          value={unrealizedPL != null ? fmtCurrency(unrealizedPL) : '—'}
          color={plColor}
          loading={accountLoading}
        />
        <MetricCard
          label="Active Trades"
          value={tradesLoading ? '—' : openTradeCount.toString()}
          sub={<Link to="/portfolio" className="text-text-secondary hover:text-white hover:underline">View →</Link>}
          loading={tradesLoading}
        />
        <MetricCard
          label="Active Signals"
          value={signalsLoading ? '—' : approvedSignals.length.toString()}
          sub={`${activeSignals.length} total`}
          loading={signalsLoading}
        />
        <MetricCard
          label="Win Rate"
          value={winRate}
          sub={`${totalClosed} trades`}
        />
      </div>

      {/* Chart + signals */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 card space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="font-medium text-text-primary">Chart</h2>
            <div className="flex items-center gap-2">
              <PairSelector value={pair} onChange={setPair} />
              <TimeframeSelector value={timeframe} onChange={setTimeframe} />
            </div>
          </div>
          <ErrorBoundary><ChartWidget pair={pair} timeframe={timeframe} height={340} /></ErrorBoundary>
        </div>

        <div className="space-y-4">
          {/* Active signals */}
          <div className="card">
            <h2 className="font-medium text-text-primary mb-3">Active Signals</h2>
            {signalsLoading ? (
              <div className="space-y-2">{[0,1].map(i => <div key={i} className="skeleton h-20" />)}</div>
            ) : approvedSignals.length === 0 ? (
              <p className="text-text-muted text-sm">No approved signals right now.</p>
            ) : (
              <div className="space-y-2 max-h-72 overflow-y-auto">
                {approvedSignals.slice(0, 3).map(s => (
                  <SignalCard key={s.id} signal={s} compact onAction={refetchSignals} />
                ))}
              </div>
            )}
          </div>

          {/* Open positions summary */}
          {openTrades && openTrades.length > 0 && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-medium text-text-primary">Open Positions</h2>
                <Link to="/portfolio" className="text-xs text-text-secondary hover:text-white hover:underline">Details →</Link>
              </div>
              <div className="space-y-2">
                {openTrades.slice(0, 4).map(t => {
                  const pl = parseFloat(t.unrealizedPL || t.unrealized_pl || 0)
                  const isLong = parseFloat(t.currentUnits || t.units || 0) > 0
                  return (
                    <div key={t.id} className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{t.instrument?.replace('_', '/')}</span>
                        <span className={`text-xs ${isLong ? 'text-long' : 'text-short'}`}>
                          {isLong ? 'LONG' : 'SHORT'}
                        </span>
                      </div>
                      <span className={`font-mono ${pl >= 0 ? 'text-long' : 'text-short'}`}>
                        {fmtCurrency(pl)}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* News */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-medium text-text-primary">Upcoming News</h2>
              <Link to="/news" className="text-xs text-text-secondary hover:text-white hover:underline">All →</Link>
            </div>
            <NewsCalendar limit={3} hours={24} />
          </div>
        </div>
      </div>
    </div>
  )
}
