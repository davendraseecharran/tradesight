import { useState } from 'react'
import { apiFetch, ENDPOINTS, API_BASE } from '../utils/api'
import PairSelector from '../components/PairSelector'
import { fmtPct, fmtUSD } from '../utils/formatters'

const STRATEGIES = [
  { value: 'ema_crossover', label: 'EMA Crossover' },
  { value: 'rsi_mean_reversion', label: 'RSI Mean Reversion' },
  { value: 'macd_momentum', label: 'MACD Momentum' },
  { value: 'mtf_confluence', label: 'MTF Confluence' },
]

function MetricRow({ label, value, color }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-bg-border last:border-0">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className={`text-sm font-semibold font-mono ${color ?? 'text-text-primary'}`}>{value}</span>
    </div>
  )
}

export default function Backtest() {
  const [pair, setPair] = useState('EUR_USD')
  const [strategy, setStrategy] = useState('ema_crossover')
  const [months, setMonths] = useState(6)
  const [loading, setLoading] = useState(false)
  const [comparing, setComparing] = useState(false)
  const [result, setResult] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [error, setError] = useState(null)

  const runBacktest = async () => {
    setLoading(true); setError(null); setResult(null); setComparison(null)
    try {
      const url = `${ENDPOINTS.runBacktest}?instrument=${pair}&strategy_name=${strategy}&months=${months}&granularity=4H`
      const data = await apiFetch(url, { method: 'POST' })
      setResult(data)
    } catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }

  const runComparison = async () => {
    setComparing(true); setError(null); setComparison(null)
    try {
      const url = `${ENDPOINTS.compareStrategies}?instrument=${pair}&months=${months}&granularity=4H`
      const data = await apiFetch(url, { method: 'POST' })
      setComparison(data)
    } catch (err) { setError(err.message) }
    finally { setComparing(false) }
  }

  const m = result?.metrics

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">Backtest</h1>

      {/* Config */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Configuration</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <p className="label mb-1">Pair</p>
            <PairSelector value={pair} onChange={setPair} />
          </div>
          <div>
            <p className="label mb-1">Strategy</p>
            <select value={strategy} onChange={e => setStrategy(e.target.value)}
              className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5">
              {STRATEGIES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <p className="label mb-1">Months</p>
            <input type="number" min="1" max="24" value={months} onChange={e => setMonths(+e.target.value)}
              className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-20" />
          </div>
          <button onClick={runBacktest} disabled={loading} className="btn-primary">
            {loading ? 'Running…' : 'Run Backtest'}
          </button>
          <button onClick={runComparison} disabled={comparing} className="btn-secondary">
            {comparing ? 'Comparing…' : 'Compare All'}
          </button>
        </div>
      </div>

      {error && <div className="bg-short/10 border border-short/30 text-short text-sm px-4 py-3 rounded-md">{error}</div>}

      {/* Single result */}
      {result && m && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <h2 className="font-medium text-text-primary mb-2">Results — {pair} {strategy}</h2>
            <MetricRow label="Total Trades" value={m.total_trades} />
            <MetricRow label="Win Rate" value={fmtPct(m.win_rate)} color={m.win_rate >= 0.5 ? 'text-long' : 'text-short'} />
            <MetricRow label="Total Return" value={fmtPct(m.total_return)} color={m.total_return >= 0 ? 'text-long' : 'text-short'} />
            <MetricRow label="Max Drawdown" value={fmtPct(m.max_drawdown)} color="text-short" />
            <MetricRow label="Sharpe Ratio" value={m.sharpe_ratio?.toFixed(2) ?? '—'} />
            <MetricRow label="Profit Factor" value={m.profit_factor?.toFixed(2) ?? '—'} color={m.profit_factor >= 1 ? 'text-long' : 'text-short'} />
            <MetricRow label="Expectancy" value={fmtUSD(m.expectancy)} color={m.expectancy >= 0 ? 'text-long' : 'text-short'} />
          </div>
          <div className="card">
            <h2 className="font-medium text-text-primary mb-2">Trade Summary</h2>
            <MetricRow label="Winning Trades" value={m.winning_trades} color="text-long" />
            <MetricRow label="Losing Trades" value={m.losing_trades} color="text-short" />
            <MetricRow label="Avg Win" value={fmtUSD(m.avg_win)} color="text-long" />
            <MetricRow label="Avg Loss" value={fmtUSD(m.avg_loss)} color="text-short" />
            <MetricRow label="Gross Profit" value={fmtUSD(m.gross_profit)} color="text-long" />
            <MetricRow label="Gross Loss" value={fmtUSD(m.gross_loss)} color="text-short" />
            <MetricRow label="Final Balance" value={fmtUSD(m.final_balance)} />
          </div>
        </div>
      )}

      {/* Comparison */}
      {comparison?.comparison && (
        <div className="card overflow-x-auto">
          <h2 className="font-medium text-text-primary mb-3">Strategy Comparison — {pair}</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-bg-border text-left">
                {['Strategy', 'Trades', 'Win Rate', 'Return', 'Drawdown', 'Sharpe', 'Profit Factor'].map(h => (
                  <th key={h} className="label pb-2 pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(comparison.comparison).map(([name, m]) => (
                <tr key={name} className="border-b border-bg-border/50 hover:bg-bg-hover/50">
                  <td className="py-2 pr-4 font-medium">{name}</td>
                  <td className="py-2 pr-4 font-mono">{m.total_trades}</td>
                  <td className={`py-2 pr-4 font-mono ${m.win_rate >= 0.5 ? 'text-long' : 'text-short'}`}>{fmtPct(m.win_rate)}</td>
                  <td className={`py-2 pr-4 font-mono ${m.total_return >= 0 ? 'text-long' : 'text-short'}`}>{fmtPct(m.total_return)}</td>
                  <td className="py-2 pr-4 font-mono text-short">{fmtPct(m.max_drawdown)}</td>
                  <td className="py-2 pr-4 font-mono">{m.sharpe_ratio?.toFixed(2) ?? '—'}</td>
                  <td className={`py-2 pr-4 font-mono ${m.profit_factor >= 1 ? 'text-long' : 'text-short'}`}>{m.profit_factor?.toFixed(2) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
