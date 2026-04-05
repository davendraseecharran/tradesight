import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts'
import { ENDPOINTS, apiFetch } from '../utils/api'

export default function ChartWidget({ pair, timeframe, height = 400, signalLevels = null }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volSeriesRef = useRef(null)
  const levelLinesRef = useRef([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Init chart once
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#1a2535' },
        textColor: '#c8d6e5',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: '#253248' },
        horzLines: { color: '#253248' },
      },
      crosshair: { mode: 1 },
      rightPriceScale: {
        borderColor: '#253248',
        textColor: '#c8d6e5',
      },
      timeScale: {
        borderColor: '#253248',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => {
          const d = new Date(time * 1000)
          const mon = d.toLocaleString('en', { month: 'short' })
          const day = d.getDate()
          return `${mon} ${day}`
        },
      },
      width: containerRef.current.clientWidth,
      height,
    })

    // v5 API: chart.addSeries(SeriesType, options)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    const volSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      color: '#253248',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volSeriesRef.current = volSeries

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [height])

  // Load data when pair/timeframe changes
  useEffect(() => {
    if (!candleSeriesRef.current) return
    let cancelled = false
    setLoading(true)
    setError(null)

    apiFetch(ENDPOINTS.chartCandles(pair, timeframe, 300))
      .then(res => {
        if (cancelled) return
        const candles = (res.candles || []).filter(c => c.open && c.high && c.low && c.close)
        candleSeriesRef.current.setData(candles.map(c => ({
          time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
        })))
        volSeriesRef.current.setData(candles.map(c => ({
          time: c.time, value: c.volume || 0,
          color: c.close >= c.open ? 'rgba(38,166,154,0.3)' : 'rgba(239,83,80,0.3)',
        })))
        chartRef.current.timeScale().fitContent()
        setLoading(false)
      })
      .catch(err => {
        if (!cancelled) { setError(err.message); setLoading(false) }
      })

    return () => { cancelled = true }
  }, [pair, timeframe])

  // Draw signal level lines
  useEffect(() => {
    if (!candleSeriesRef.current) return
    levelLinesRef.current.forEach(l => { try { candleSeriesRef.current.removePriceLine(l) } catch {} })
    levelLinesRef.current = []

    if (!signalLevels) return
    const lines = [
      { price: signalLevels.entry_price, color: '#2962ff', title: 'Entry', style: 0 },
      { price: signalLevels.stop_loss, color: '#ef5350', title: 'SL', style: 2 },
      { price: signalLevels.take_profit_1, color: '#26a69a', title: 'TP1', style: 2 },
      signalLevels.take_profit_2 && { price: signalLevels.take_profit_2, color: '#26a69a', title: 'TP2', style: 2 },
    ].filter(Boolean)

    lines.forEach(cfg => {
      const line = candleSeriesRef.current.createPriceLine({
        price: cfg.price, color: cfg.color, lineWidth: 1,
        lineStyle: cfg.style, axisLabelVisible: true, title: cfg.title,
      })
      levelLinesRef.current.push(line)
    })
  }, [signalLevels])

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={containerRef} className="w-full h-full rounded-md overflow-hidden" />
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-bg-card/80 rounded-md">
          <div className="text-text-muted text-sm">Loading chart data...</div>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-bg-card/80 rounded-md">
          <div className="text-text-muted text-sm text-center">
            <p className="text-warn mb-1">Chart unavailable</p>
            <p className="text-xs">{error}</p>
          </div>
        </div>
      )}
    </div>
  )
}
