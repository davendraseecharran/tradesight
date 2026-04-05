import { useState } from 'react'
import { useApi, usePost } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import ErrorBoundary from '../components/ErrorBoundary'
import ChartWidget from '../components/ChartWidget'
import PairSelector from '../components/PairSelector'
import TimeframeSelector from '../components/TimeframeSelector'
import { fmtPrice, pairDecimals } from '../utils/formatters'

function IndicatorGrid({ data }) {
  if (!data?.indicators) return null
  const { indicators: ind, price } = data
  const d = pairDecimals(data.instrument)

  const items = [
    { label: 'Price', value: fmtPrice(price, d) },
    { label: 'RSI 14', value: ind.rsi_14?.toFixed(1) ?? '—', color: ind.rsi_14 > 70 ? 'text-short' : ind.rsi_14 < 30 ? 'text-long' : undefined },
    { label: 'EMA 20', value: fmtPrice(ind.ema_20, d) },
    { label: 'EMA 50', value: fmtPrice(ind.ema_50, d) },
    { label: 'EMA 200', value: fmtPrice(ind.ema_200, d) },
    { label: 'MACD', value: ind.macd_line?.toFixed(5) ?? '—', color: ind.macd_line > ind.macd_signal ? 'text-long' : 'text-short' },
    { label: 'MACD Signal', value: ind.macd_signal?.toFixed(5) ?? '—' },
    { label: 'BB Upper', value: fmtPrice(ind.bb_upper, d) },
    { label: 'BB Lower', value: fmtPrice(ind.bb_lower, d) },
    { label: 'ATR 14', value: ind.atr_14?.toFixed(5) ?? '—' },
    { label: 'VWAP', value: fmtPrice(ind.vwap, d) },
    { label: 'Ichimoku T', value: fmtPrice(ind.ichimoku_tenkan, d) },
  ]

  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
      {items.map(({ label, value, color }) => (
        <div key={label} className="bg-bg-secondary border border-bg-border rounded px-2 py-2">
          <p className="label text-[10px]">{label}</p>
          <p className={`font-mono text-sm font-medium ${color ?? 'text-text-primary'}`}>{value}</p>
        </div>
      ))}
    </div>
  )
}

export default function Charts() {
  const [pair, setPair] = useState('EUR_USD')
  const [timeframe, setTimeframe] = useState('4H')
  const [signal, setSignal] = useState(null)
  const [analysisMsg, setAnalysisMsg] = useState(null)

  const { data: indicators, loading: indLoading, refetch: refetchInd } = useApi(
    ENDPOINTS.chartIndicators(pair, timeframe),
    { deps: [pair, timeframe] }
  )

  const { post: analyze, loading: analyzing } = usePost(ENDPOINTS.analyzePair(pair))

  const handleAnalyze = async () => {
    setAnalysisMsg(null)
    setSignal(null)
    const { data, error } = await analyze()
    if (error) {
      if (error.toLowerCase().includes('credit') || error.toLowerCase().includes('fund')) {
        setAnalysisMsg({ type: 'info', text: 'AI analysis is not available — Anthropic API credits needed. Add credits at console.anthropic.com.' })
      } else {
        setAnalysisMsg({ type: 'error', text: error })
      }
      return
    }
    if (data?.status === 'no_setup') {
      setAnalysisMsg({ type: 'info', text: `No setup found for ${pair} (confidence: ${data.confidence}/10). ${data.reasoning?.slice(0, 120)}…` })
    } else if (data?.direction) {
      setSignal(data)
      setAnalysisMsg({ type: 'success', text: `${pair} ${data.direction.toUpperCase()} signal — confidence ${data.confidence}/10` })
    }
  }

  const handlePairChange = (p) => { setPair(p); setSignal(null); setAnalysisMsg(null) }
  const handleTfChange = (tf) => { setTimeframe(tf); setSignal(null); setAnalysisMsg(null) }

  const signalLevels = signal ? {
    entry_price: signal.entry_price,
    stop_loss: signal.stop_loss,
    take_profit_1: signal.take_profit_1,
    take_profit_2: signal.take_profit_2,
  } : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-lg font-semibold">Charts</h1>
        <div className="flex items-center gap-2">
          <PairSelector value={pair} onChange={handlePairChange} />
          <TimeframeSelector value={timeframe} onChange={handleTfChange} />
          <button onClick={handleAnalyze} disabled={analyzing} className="btn-primary">
            {analyzing ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>
      </div>

      {analysisMsg && (
        <div className={`px-4 py-3 rounded-md text-sm border ${
          analysisMsg.type === 'success' ? 'bg-long/10 border-long/30 text-long' :
          analysisMsg.type === 'error'   ? 'bg-short/10 border-short/30 text-short' :
                                           'bg-bg-card border-bg-border text-text-secondary'
        }`}>
          {analysisMsg.text}
        </div>
      )}

      <div className="card">
        <ErrorBoundary><ChartWidget pair={pair} timeframe={timeframe} height={460} signalLevels={signalLevels} /></ErrorBoundary>
      </div>

      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Indicator Readings — {pair} {timeframe}</h2>
        {indLoading ? (
          <div className="grid grid-cols-6 gap-2">{Array(12).fill(0).map((_, i) => <div key={i} className="skeleton h-12" />)}</div>
        ) : (
          <IndicatorGrid data={indicators} />
        )}
      </div>
    </div>
  )
}
