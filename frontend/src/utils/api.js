export const API_BASE = 'http://localhost:8000'

export const ENDPOINTS = {
  // Account
  accountSummary: `${API_BASE}/api/v1/account/summary`,
  positions: `${API_BASE}/api/v1/account/positions`,
  // Chart data
  chartCandles: (pair, tf, count = 200) =>
    `${API_BASE}/api/v1/chart/candles/${pair}?timeframe=${tf}&count=${count}`,
  chartIndicators: (pair, tf) =>
    `${API_BASE}/api/v1/chart/indicators/${pair}?timeframe=${tf}`,
  // Signals
  activeSignals: `${API_BASE}/api/v1/signals/`,
  signalHistory: (limit = 50) => `${API_BASE}/api/v1/signals/history?limit=${limit}`,
  signalSchedule: `${API_BASE}/api/v1/signals/schedule`,
  analyzePair: (pair) => `${API_BASE}/api/v1/signals/analyze/${pair}`,
  setExecutionMode: `${API_BASE}/api/v1/signals/settings/mode`,
  // Trades (Phase 5)
  executeManualTrade: `${API_BASE}/api/v1/trade/execute`,
  openTrades: `${API_BASE}/api/v1/trade/open`,
  tradeHistory: (count = 50) => `${API_BASE}/api/v1/trade/history?count=${count}`,
  closeTrade: (tradeId) => `${API_BASE}/api/v1/trade/${tradeId}/close`,
  breakevenTrade: (tradeId) => `${API_BASE}/api/v1/trade/${tradeId}/breakeven`,
  approveSignal: (signalId) => `${API_BASE}/api/v1/signals/${signalId}/approve`,
  rejectSignal: (signalId) => `${API_BASE}/api/v1/signals/${signalId}/reject`,
  // Backtest
  runBacktest: `${API_BASE}/api/v1/backtest/run`,
  compareStrategies: `${API_BASE}/api/v1/backtest/compare`,
  walkForward: `${API_BASE}/api/v1/backtest/walk-forward`,
  // News
  newsCalendar: (hours = 48) => `${API_BASE}/api/v1/news/calendar?hours_ahead=${hours}`,
  refreshNews: `${API_BASE}/api/v1/news/refresh`,
  // Tokens
  tokenUsage: `${API_BASE}/api/v1/tokens/usage`,
  // Settings
  getConfig: `${API_BASE}/api/v1/settings/config`,
  updateConfig: `${API_BASE}/api/v1/settings/config`,
  testEmail: `${API_BASE}/api/v1/settings/test-email`,
  // Health
  health: `${API_BASE}/health`,
  // Diagnostic report download (days=0 → all history)
  reportExport: (days = 7) => `${API_BASE}/api/v1/report/export?days=${days}`,
}

export async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}
