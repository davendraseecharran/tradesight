import { useState, useEffect } from 'react'
import { apiFetch, ENDPOINTS } from '../utils/api'

const MODES = [
  { value: 'ALERT_ONLY', label: 'Alert Only', desc: 'Generates signals and sends email alerts. No automatic trading.' },
  { value: 'SEMI_AUTO',  label: 'Semi-Auto',  desc: 'Sends alerts and logs signals. You confirm trades in MetaTrader.' },
  { value: 'FULL_AUTO',  label: 'Full Auto',  desc: 'Executes trades automatically. Use with caution.' },
]

const TRADING_WINDOWS = [
  { label: 'London Open',       time: '6:00 – 8:00 AM ET',  note: 'High volatility, best setups' },
  { label: 'NY-London Overlap', time: '4:00 – 7:00 PM ET',  note: 'Highest liquidity of the day' },
  { label: 'NY Session',        time: '7:00 – 11:00 PM ET', note: 'USD pairs active' },
]

const PAIRS = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'GBP_JPY', 'AUD_USD', 'USD_CAD']

const DEFAULTS = {
  mode: 'ALERT_ONLY',
  maxRisk: 2,
  dailyLossLimit: 5,
  maxPositions: 3,
  minRR: 2.0,
  activePairs: PAIRS,
  emailTo: '',
}

export default function Settings() {
  const [settings, setSettings] = useState(() => {
    try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem('ts_settings') || '{}') } }
    catch { return DEFAULTS }
  })
  const [saved, setSaved] = useState(false)
  const [modeError, setModeError] = useState(null)

  const update = (key, val) => setSettings(s => ({ ...s, [key]: val }))

  const togglePair = (pair) => {
    setSettings(s => ({
      ...s,
      activePairs: s.activePairs.includes(pair)
        ? s.activePairs.filter(p => p !== pair)
        : [...s.activePairs, pair],
    }))
  }

  const handleSave = async () => {
    localStorage.setItem('ts_settings', JSON.stringify(settings))
    try {
      await apiFetch(`${ENDPOINTS.setExecutionMode}?mode=${settings.mode}`, { method: 'POST' })
    } catch (err) { setModeError(err.message) }
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-lg font-semibold">Settings</h1>

      {/* Execution Mode */}
      <div className="card space-y-3">
        <h2 className="font-medium text-text-primary">Execution Mode</h2>
        {MODES.map(m => (
          <label key={m.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            settings.mode === m.value ? 'border-brand bg-brand/10' : 'border-bg-border hover:border-bg-hover'
          }`}>
            <input type="radio" name="mode" value={m.value} checked={settings.mode === m.value}
              onChange={() => update('mode', m.value)} className="mt-0.5 accent-brand" />
            <div>
              <p className="text-sm font-medium text-text-primary">{m.label}</p>
              <p className="text-xs text-text-muted mt-0.5">{m.desc}</p>
            </div>
          </label>
        ))}
        {modeError && <p className="text-xs text-short">Could not apply mode to server: {modeError}</p>}
      </div>

      {/* Trading Windows */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Trading Windows (ET)</h2>
        <div className="space-y-2">
          {TRADING_WINDOWS.map(w => (
            <div key={w.label} className="flex items-center justify-between py-2 border-b border-bg-border last:border-0 text-sm">
              <div>
                <p className="text-text-primary font-medium">{w.label}</p>
                <p className="text-xs text-text-muted">{w.note}</p>
              </div>
              <span className="font-mono text-brand">{w.time}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Active Pairs */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Active Pairs</h2>
        <div className="grid grid-cols-3 gap-2">
          {PAIRS.map(pair => (
            <label key={pair} className={`flex items-center gap-2 px-3 py-2 rounded-md border cursor-pointer text-sm ${
              settings.activePairs.includes(pair) ? 'border-brand bg-brand/10 text-brand' : 'border-bg-border text-text-muted'
            }`}>
              <input type="checkbox" checked={settings.activePairs.includes(pair)}
                onChange={() => togglePair(pair)} className="accent-brand" />
              {pair.replace('_', '/')}
            </label>
          ))}
        </div>
      </div>

      {/* Risk Parameters */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Risk Parameters</h2>
        <div className="grid grid-cols-2 gap-4">
          {[
            { label: 'Max Risk Per Trade (%)', key: 'maxRisk', min: 0.5, max: 5, step: 0.5 },
            { label: 'Daily Loss Limit (%)', key: 'dailyLossLimit', min: 1, max: 20, step: 1 },
            { label: 'Max Open Positions', key: 'maxPositions', min: 1, max: 10, step: 1 },
            { label: 'Min Risk/Reward Ratio', key: 'minRR', min: 1, max: 5, step: 0.5 },
          ].map(f => (
            <div key={f.key}>
              <label className="label mb-1 block">{f.label}</label>
              <input
                type="number" min={f.min} max={f.max} step={f.step}
                value={settings[f.key]}
                onChange={e => update(f.key, parseFloat(e.target.value))}
                className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-full focus:outline-none focus:border-brand"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Email */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Email Alerts</h2>
        <p className="text-xs text-text-muted mb-3">Configure SMTP credentials in your <code className="bg-bg-hover px-1 rounded">.env</code> file. Email address here is stored locally.</p>
        <div>
          <label className="label mb-1 block">Alert Email To</label>
          <input
            type="email" placeholder="you@example.com" value={settings.emailTo}
            onChange={e => update('emailTo', e.target.value)}
            className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-full focus:outline-none focus:border-brand"
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={handleSave} className="btn-primary">Save Settings</button>
        {saved && <span className="text-long text-sm">✓ Settings saved</span>}
      </div>
    </div>
  )
}
