export function fmtPrice(val, decimals = 5) {
  if (val == null) return '—'
  return Number(val).toFixed(decimals)
}

export function fmtCurrency(val, decimals = 2) {
  if (val == null) return '—'
  const n = Number(val)
  return (n >= 0 ? '+' : '') + n.toFixed(decimals)
}

export function fmtUSD(val) {
  if (val == null) return '—'
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function fmtPct(val) {
  if (val == null) return '—'
  return (Number(val) * 100).toFixed(2) + '%'
}

export function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  })
}

export function fmtDateShort(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function fmtTimeAgo(iso) {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function fmtPair(pair) {
  return pair?.replace('_', '/') ?? '—'
}

export function pairDecimals(pair) {
  return pair?.includes('JPY') ? 3 : 5
}
