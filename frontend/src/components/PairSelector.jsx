const PAIRS = ['EUR_USD', 'GBP_USD', 'USD_JPY', 'GBP_JPY', 'AUD_USD', 'USD_CAD']

export default function PairSelector({ value, onChange, className = '' }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className={`bg-bg-card border border-bg-border text-text-primary text-sm rounded-md px-3 py-1.5 focus:outline-none focus:border-brand ${className}`}
    >
      {PAIRS.map(p => (
        <option key={p} value={p}>{p.replace('_', '/')}</option>
      ))}
    </select>
  )
}
