import { useState, useEffect } from 'react'
import { apiFetch, ENDPOINTS } from '../utils/api'
import { useApi } from '../hooks/useApi'

// Every control on this page reads from and writes to the backend's .env
// via /api/v1/settings/config. There is no browser-local state — what you
// see here is what the bot actually uses. Writes are only accepted from
// the trading Mac itself (remote devices are view-only).

const MODES = [
  { value: 'ALERT_ONLY', label: 'Alert Only', desc: 'Generates signals and sends email alerts. No automatic trading.' },
  { value: 'SEMI_AUTO',  label: 'Semi-Auto',  desc: 'Sends alerts and logs signals. You confirm trades in the UI.' },
  { value: 'FULL_AUTO',  label: 'Full Auto',  desc: 'Executes trades automatically when the engine, AI validator, and risk manager all approve.' },
]

const VALIDATOR_MODES = [
  { value: 'required', label: 'Required', desc: 'No AI validation = no trade (safest). Trading pauses if the Claude API is unavailable.' },
  { value: 'optional', label: 'Optional', desc: 'Trade on engine rules alone if the AI validator is unavailable.' },
  { value: 'off',      label: 'Off',      desc: 'Pure mechanical engine. No AI calls in the trade path.' },
]

const OANDA_ENVS = [
  { value: 'https://api-fxpractice.oanda.com', label: 'Practice (paper trading)' },
  { value: 'https://api-fxtrade.oanda.com',    label: 'LIVE — real money' },
]

const SCHEDULE = [
  { label: 'Market scan (engine + AI validator)', time: '1:05, 5:05, 9:05 AM/PM ET', note: 'Right after each 4-hour candle closes' },
  { label: 'Candle data refresh',                 time: 'Hourly + at startup',        note: 'Keeps charts and engine data current' },
  { label: 'Open-trade management',               time: 'Every 5 minutes',            note: 'Breakeven at 1R, partial close at TP1, trailing at 2R' },
  { label: 'Daily status email',                  time: '5:15 PM ET',                 note: 'No email = app is down' },
]

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

// .env stores decimals (0.02); the UI shows percentages (2)
const PCT_KEYS = new Set(['MAX_RISK_PER_TRADE', 'DAILY_LOSS_LIMIT'])
const toDisplay = (key, val) => {
  if (PCT_KEYS.has(key) && val !== '' && !isNaN(parseFloat(val))) {
    return String(parseFloat(val) * 100)
  }
  return val
}
const toEnv = (key, val) => {
  if (PCT_KEYS.has(key) && val !== '' && !isNaN(parseFloat(val))) {
    return String(parseFloat(val) / 100)
  }
  return val
}

export default function Settings() {
  const [config, setConfig] = useState({})
  const [edits, setEdits] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState(null)
  const [emailSending, setEmailSending] = useState(false)

  const { data: schedule } = useApi(ENDPOINTS.signalSchedule)
  const pairs = schedule?.valid_pairs || []

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await apiFetch(ENDPOINTS.getConfig)
      setConfig(data.config || {})
      setEdits({})
    } catch (err) {
      setToast({ message: `Failed to load config: ${err.message}`, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadConfig() }, [])

  const getVal = (key) => {
    if (key in edits) return edits[key]
    return toDisplay(key, config[key] ?? '')
  }
  const setVal = (key, val) => setEdits(e => ({ ...e, [key]: val }))
  const dirty = Object.keys(edits).length > 0

  const handleSave = async () => {
    const updates = {}
    for (const [key, val] of Object.entries(edits)) {
      const envVal = toEnv(key, val)
      // Skip untouched masked secrets and unchanged values
      if (val !== '' && !String(val).startsWith('***') && envVal !== config[key]) {
        updates[key] = envVal
      }
    }
    if (Object.keys(updates).length === 0) {
      setToast({ message: 'No changes to save', type: 'error' })
      return
    }
    setSaving(true)
    try {
      await apiFetch(ENDPOINTS.updateConfig, {
        method: 'POST',
        body: JSON.stringify({ updates }),
      })
      setToast({
        message: `Saved ${Object.keys(updates).length} setting(s) — live on the next scheduled run.`,
        type: 'success',
      })
      await loadConfig()
    } catch (err) {
      setToast({ message: `Save failed: ${err.message}`, type: 'error' })
    } finally {
      setSaving(false)
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

  if (loading) {
    return (
      <div className="space-y-4 max-w-3xl">
        <h1 className="text-lg font-semibold">Settings</h1>
        <div className="space-y-2">{[0, 1, 2, 3].map(i => <div key={i} className="skeleton h-24" />)}</div>
      </div>
    )
  }

  return (
    <div className="space-y-4 max-w-3xl pb-20">
      <h1 className="text-lg font-semibold">Settings</h1>

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      {/* Connections */}
      <div className="card space-y-4">
        <h2 className="font-medium text-text-primary">API Keys & Connections</h2>
        <p className="text-xs text-text-muted">
          Saved values apply immediately — no server restart, no file editing.
          Secrets display masked (***) until replaced.
        </p>

        <div className="space-y-3">
          <p className="text-xs text-text-muted font-medium uppercase tracking-wide">OANDA</p>
          <div>
            <label className="label mb-1 block">Environment</label>
            <select
              value={getVal('OANDA_API_URL')}
              onChange={e => setVal('OANDA_API_URL', e.target.value)}
              className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-full focus:outline-none focus:border-neutral-500"
            >
              {OANDA_ENVS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {getVal('OANDA_API_URL').includes('fxtrade') && (
              <p className="text-xs text-short mt-1">
                LIVE environment selected — trades will use real money. Make sure the token and
                account ID below belong to the live account.
              </p>
            )}
          </div>
          <ConfigField label="API Token" value={getVal('OANDA_API_TOKEN')} onChange={v => setVal('OANDA_API_TOKEN', v)} type="password" />
          <ConfigField label="Account ID" value={getVal('OANDA_ACCOUNT_ID')} onChange={v => setVal('OANDA_ACCOUNT_ID', v)} placeholder="101-001-XXXXXXXX-XXX" />
        </div>

        <div className="space-y-3 pt-2 border-t border-bg-border">
          <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Anthropic (AI validator)</p>
          <ConfigField label="API Key" value={getVal('ANTHROPIC_API_KEY')} onChange={v => setVal('ANTHROPIC_API_KEY', v)} type="password" />
        </div>

        <div className="space-y-3 pt-2 border-t border-bg-border">
          <p className="text-xs text-text-muted font-medium uppercase tracking-wide">Email Alerts</p>
          <ConfigField label="Alert Email To" value={getVal('ALERT_EMAIL_TO')} onChange={v => setVal('ALERT_EMAIL_TO', v)} placeholder="you@example.com" />
          <ConfigField label="SMTP Username (From)" value={getVal('SMTP_USERNAME')} onChange={v => setVal('SMTP_USERNAME', v)} placeholder="you@gmail.com" />
          <div className="grid grid-cols-2 gap-3">
            <ConfigField label="SMTP Host" value={getVal('SMTP_HOST')} onChange={v => setVal('SMTP_HOST', v)} />
            <ConfigField label="SMTP Port" value={getVal('SMTP_PORT')} onChange={v => setVal('SMTP_PORT', v)} />
          </div>
          <ConfigField label="SMTP Password (app password)" value={getVal('SMTP_PASSWORD')} onChange={v => setVal('SMTP_PASSWORD', v)} type="password" />
          <div className="flex items-center gap-3">
            <button onClick={handleTestEmail} disabled={emailSending}
              className="px-4 py-2 text-sm rounded-md border border-bg-border text-text-secondary hover:bg-bg-hover transition disabled:opacity-50">
              {emailSending ? 'Sending...' : 'Send Test Email'}
            </button>
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={String(getVal('DAILY_STATUS_EMAIL') || 'true').toLowerCase() !== 'false'}
                onChange={e => setVal('DAILY_STATUS_EMAIL', e.target.checked ? 'true' : 'false')}
                className="accent-white"
              />
              Daily status email (5:15 PM ET heartbeat)
            </label>
          </div>
        </div>
      </div>

      {/* Execution */}
      <div className="card space-y-3">
        <h2 className="font-medium text-text-primary">Execution Mode</h2>
        {MODES.map(m => (
          <label key={m.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            getVal('EXECUTION_MODE') === m.value ? 'border-white/40 bg-white/5' : 'border-bg-border hover:border-bg-hover'
          }`}>
            <input type="radio" name="mode" value={m.value} checked={getVal('EXECUTION_MODE') === m.value}
              onChange={() => setVal('EXECUTION_MODE', m.value)} className="mt-0.5 accent-white" />
            <div>
              <p className="text-sm font-medium text-text-primary">{m.label}</p>
              <p className="text-xs text-text-muted mt-0.5">{m.desc}</p>
            </div>
          </label>
        ))}

        <h2 className="font-medium text-text-primary pt-2 border-t border-bg-border">AI Validator</h2>
        {VALIDATOR_MODES.map(m => (
          <label key={m.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
            (getVal('VALIDATOR_MODE') || 'required') === m.value ? 'border-white/40 bg-white/5' : 'border-bg-border hover:border-bg-hover'
          }`}>
            <input type="radio" name="validator" value={m.value} checked={(getVal('VALIDATOR_MODE') || 'required') === m.value}
              onChange={() => setVal('VALIDATOR_MODE', m.value)} className="mt-0.5 accent-white" />
            <div>
              <p className="text-sm font-medium text-text-primary">{m.label}</p>
              <p className="text-xs text-text-muted mt-0.5">{m.desc}</p>
            </div>
          </label>
        ))}
      </div>

      {/* Risk Parameters — wired to the real .env, not browser storage */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-1">Risk Parameters</h2>
        <p className="text-xs text-text-muted mb-3">
          These are the actual limits the risk manager enforces on every trade.
        </p>
        <div className="grid grid-cols-2 gap-4">
          {[
            { label: 'Max Risk Per Trade (%)', key: 'MAX_RISK_PER_TRADE', min: 0.5, max: 5, step: 0.5 },
            { label: 'Daily Loss Limit (%)', key: 'DAILY_LOSS_LIMIT', min: 1, max: 10, step: 0.5 },
            { label: 'Max Open Positions', key: 'MAX_OPEN_POSITIONS', min: 1, max: 10, step: 1 },
            { label: 'Min Risk/Reward Ratio', key: 'MIN_RISK_REWARD_RATIO', min: 1, max: 5, step: 0.5 },
            { label: 'Min AI Confidence (1-10)', key: 'ANALYST_MIN_CONFIDENCE', min: 5, max: 10, step: 1 },
          ].map(f => (
            <div key={f.key}>
              <label className="label mb-1 block">{f.label}</label>
              <input
                type="number" min={f.min} max={f.max} step={f.step}
                value={getVal(f.key)}
                onChange={e => setVal(f.key, e.target.value)}
                className="bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 w-full focus:outline-none focus:border-neutral-500"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Real schedule (read-only) */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-3">Automation Schedule</h2>
        <div className="space-y-2">
          {SCHEDULE.map(w => (
            <div key={w.label} className="flex items-center justify-between py-2 border-b border-bg-border last:border-0 text-sm">
              <div>
                <p className="text-text-primary font-medium">{w.label}</p>
                <p className="text-xs text-text-muted">{w.note}</p>
              </div>
              <span className="font-mono text-text-primary text-xs">{w.time}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Traded markets (read-only, from the backend) */}
      <div className="card">
        <h2 className="font-medium text-text-primary mb-1">Traded Markets</h2>
        <p className="text-xs text-text-muted mb-3">
          Markets the engine scans every cycle. Adding/removing markets is a strategy
          change (each needs a passing backtest) — request it in a Claude session.
        </p>
        <div className="flex flex-wrap gap-2">
          {pairs.map(pair => (
            <span key={pair} className="px-3 py-1.5 rounded-md border border-bg-border text-sm text-text-secondary">
              {pair.replace('_', '/')}
            </span>
          ))}
        </div>
      </div>

      {/* Sticky save bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-bg-secondary/95 border-t border-bg-border px-6 py-3 flex items-center gap-4 backdrop-blur">
        <button onClick={handleSave} disabled={!dirty || saving} className="btn-primary disabled:opacity-40">
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
        <span className="text-xs text-text-muted">
          {dirty
            ? `${Object.keys(edits).length} unsaved change(s)`
            : 'All settings live — changes apply on the next scheduled run, no restart needed.'}
        </span>
      </div>
    </div>
  )
}
