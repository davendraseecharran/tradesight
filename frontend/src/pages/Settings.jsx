import { useState, useEffect } from 'react'
import { apiFetch, ENDPOINTS } from '../utils/api'

const MODES = [
  { value: 'ALERT_ONLY', label: 'Alert Only', desc: 'Generates signals and sends email alerts. No automatic trading.' },
  { value: 'SEMI_AUTO',  label: 'Semi-Auto',  desc: 'Sends alerts and logs signals. You confirm trades in the UI.' },
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

function Toast({ message, type, onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000)
    return () => clearTimeout(t)
  }, [onClose])

  const bg = type === 'success' ? 'bg-long/20 border-long/40 text-long' : 'bg-short/20 border-short/40 text-short'
  return (
    <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg border text-sm ${bg} shadow-lg`}>
      {message}
    </div>
  )
}

function ConfigField({ label, value, onChange, type = 'text', placeholder = '' }) {
  const isPassword = type === 'password'
  const [show, setShow] = useState(false)

  return (
    <div>
      <label className="label mb-1 block">{label}</label>
      <div className="flex gap-2">
        <input
          type={isPassword && !show ? 'password' : 'text'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 flex-1 focus:outline-none focus:border-neutral-500 font-mono"
        />
        {isPassword && (
          <button onClick={() => setShow(!show)}
            className="px-2 text-xs text-text-muted border border-bg-border rounded-md hover:bg-bg-hover">
            {show ? 'Hide' : 'Show'}
          </button>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const [settings, setSettings] = useState(() => {
    try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem('ts_settings') || '{}') } }
    catch { return DEFAULTS }
  })
  const [saved, setSaved] = useState(false)
  const [modeError, setModeError] = useState(null)

  // Config editor state
  const [configOpen, setConfigOpen] = useState(false)
  const [config, setConfig] = useState({})
  const [configLoading, setConfigLoading] = useState(false)
  const [configEdits, setConfigEdits] = useState({})
  const [toast, setToast] = useState(null)
  const [emailSending, setEmailSending] = useState(false)

  const update = (key, val) => setSettings(s => ({ ...s, [key]: val }))
  const updateConfig = (key, val) => setConfigEdits(e => ({ ...e, [key]: val }))

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

  // Load config from backend
  const loadConfig = async () => {
    setConfigLoading(true)
    try {
      const data = await apiFetch(ENDPOINTS.getConfig)
      setConfig(data.config || {})
      setConfigEdits({})
    } catch (err) {
      setToast({ message: `Failed to load config: ${err.message}`, type: 'error' })
    } finally {
      setConfigLoading(false)
    }
  }

  useEffect(() => {
    if (configOpen && Object.keys(config).length === 0) {
      loadConfig()
    }
  }, [configOpen])

  const getVal = (key) => {
    if (key in configEdits) return configEdits[key]
    return config[key] || ''
  }

  const handleSaveConfig = async () => {
    // Filter out unchanged values and masked values (***...)
    const updates = {}
    for (const [key, val] of Object.entries(configEdits)) {
      if (val && !val.startsWith('***') && val !== config[key]) {
        updates[key] = val
      }
    }

    if (Object.keys(updates).length === 0) {
      setToast({ message: 'No changes to save', type: 'error' })
      return
    }

    try {
      await apiFetch(ENDPOINTS.updateConfig, {
        method: 'POST',
        body: JSON.stringify({ updates }),
      })
      setToast({ message: `Saved ${Object.keys(updates).length} setting(s). Restart server for full effect.`, type: 'success' })
      await loadConfig()
    } catch (err) {
      setToast({ message: `Save failed: ${err.message}`, type: 'error' })
    }
  }

  const handleTestEmail = async () => {
    setEmailSending(true)
    try {
      const result = await apiFetch(ENDPOINTS.testEmail, { method: 'POST' })
      setToast({ message: `Test email sent to ${result.sent_to}`, type: 'success' })
    } catch (err) {
      setToast({ message: `Email failed: ${err.message}`, type: 'error' })
    } finally {
      setEmailSending(false)
    }
  }

  return (
    <div className="space-y-4 max-w-3xl">
      <h1 className="text-lg font-semibold">Settings</h1>

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Configuration (API Keys & Connections) */}
      <div className="card">
        <button onClick={() => setConfigOpen(!configOpen)}
          className="flex items-center justify-between w-full text-left">
          <h2 className="font-medium text-text-primary">API Keys & Connections</h2>
          <span className="text-text-muted text-lg">{configOpen ? '▾' : '▸'}</span>
        </button>

        {configOpen && (
          <div className="mt-4 space-y-4">
            <div className="bg-warn/10 border border-warn/30 text-warn text-xs px-3 py-2 rounded-md">
              Changes require a server restart to take effect.
            </div>

            {configLoading ? (
              <div className="space-y-2">{[0,1,2].map(i => <div key={i} className="skeleton h-10" />)}</div>
            ) : (
              <>
                {/* OANDA */}
                <div className="space-y-3">
                  <p className="text-xs text-text-muted font-medium uppercase tracking-wide">OANDA</p>
                  <ConfigField label="API Token" value={getVal('OANDA_API_TOKEN')} onChange={v => updateConfig('OANDA_API_TOKEN', v)} type="password" />
                  <ConfigField label="Account ID" value={getVal('OANDA_ACCOUNT_ID')} onChange={v => updateConfig('OANDA_ACCOUNT_ID', v)} placeholder="101-001-XXXXXXXX-XXX" />
                </div>

                {/* Anthropic */}
                <div className="space-y-3 pt-2 border-t border-bg-border">
                  <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Anthropic</p>
                  <ConfigField label="API Key" value={getVal('ANTHROPIC_API_KEY')} onChange={v => updateConfig('ANTHROPIC_API_KEY', v)} type="password" />
                </div>

                {/* Email Settings */}
                <div className="space-y-3 pt-2 border-t border-bg-border">
                  <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Email Settings</p>
                  <ConfigField label="Alert Email To" value={getVal('ALERT_EMAIL_TO')} onChange={v => updateConfig('ALERT_EMAIL_TO', v)} type="text" placeholder="you@example.com" />
                  <ConfigField label="SMTP Username (From)" value={getVal('SMTP_USERNAME')} onChange={v => updateConfig('SMTP_USERNAME', v)} type="text" placeholder="you@gmail.com" />
                  <div className="grid grid-cols-2 gap-3">
                    <ConfigField label="SMTP Host" value={getVal('SMTP_HOST')} onChange={v => updateConfig('SMTP_HOST', v)} />
                    <ConfigField label="SMTP Port" value={getVal('SMTP_PORT')} onChange={v => updateConfig('SMTP_PORT', v)} />
                  </div>
                  <ConfigField label="SMTP Password" value={getVal('SMTP_PASSWORD')} onChange={v => updateConfig('SMTP_PASSWORD', v)} type="password" />
                </div>

                {/* Action buttons */}
                <div className="flex gap-3 pt-3 border-t border-bg-border">
                  <button onClick={handleSaveConfig} className="btn-primary">
                    Save Configuration
                  </button>
                  <button onClick={handleTestEmail} disabled={emailSending}
                    className="px-4 py-2 text-sm rounded-md border border-bg-border text-text-secondary hover:bg-bg-hover transition disabled:opacity-50">
                    {emailSending ? 'Sending...' : 'Send Test Email'}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Execution Mode */}
      <div className="card space-y-3">
        <h2 className="font-medium text-text-primary">Execution Mode</h2>
        {MODES.map(m => (
          <label key={m.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            settings.mode === m.value ? 'border-white/40 bg-white/5' : 'border-bg-border hover:border-bg-hover'
          }`}>
            <input type="radio" name="mode" value={m.value} checked={settings.mode === m.value}
              onChange={() => update('mode', m.value)} className="mt-0.5 accent-white" />
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
              <span className="font-mono text-text-primary">{w.time}</span>
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
              settings.activePairs.includes(pair) ? 'border-white/40 bg-white/5 text-white' : 'border-bg-border text-text-muted'
            }`}>
              <input type="checkbox" checked={settings.activePairs.includes(pair)}
                onChange={() => togglePair(pair)} className="accent-white" />
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
                className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-full focus:outline-none focus:border-neutral-500"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={handleSave} className="btn-primary">Save Settings</button>
        {saved && <span className="text-long text-sm">Settings saved</span>}
      </div>
    </div>
  )
}
