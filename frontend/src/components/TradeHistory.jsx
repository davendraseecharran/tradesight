import { fmtPrice, fmtDate, fmtPair, pairDecimals } from '../utils/formatters'

export default function TradeHistory({ signals }) {
  if (!signals?.length) return (
    <div className="text-center py-12 text-text-muted text-sm">No historical signals yet.</div>
  )

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-bg-border text-left">
            {['Date', 'Pair', 'Direction', 'Entry', 'SL', 'TP1', 'Confidence', 'Status'].map(h => (
              <th key={h} className="label pb-2 pr-4 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {signals.map(s => {
            const d = pairDecimals(s.instrument)
            return (
              <tr key={s.id} className="border-b border-bg-border/50 hover:bg-bg-hover/50 transition-colors">
                <td className="py-2 pr-4 text-text-muted text-xs">{fmtDate(s.created_at)}</td>
                <td className="py-2 pr-4 font-medium">{fmtPair(s.instrument)}</td>
                <td className="py-2 pr-4">
                  {s.direction ? (
                    <span className={s.direction === 'long' ? 'badge-long' : 'badge-short'}>
                      {s.direction === 'long' ? '▲ Long' : '▼ Short'}
                    </span>
                  ) : '—'}
                </td>
                <td className="py-2 pr-4 font-mono">{fmtPrice(s.entry_price, d)}</td>
                <td className="py-2 pr-4 font-mono text-short">{fmtPrice(s.stop_loss, d)}</td>
                <td className="py-2 pr-4 font-mono text-long">{fmtPrice(s.take_profit_1, d)}</td>
                <td className="py-2 pr-4">{s.confidence}/10</td>
                <td className="py-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    s.status === 'active' ? 'bg-long/20 text-long' :
                    s.status === 'cancelled' ? 'bg-short/20 text-short' :
                    'bg-bg-hover text-text-muted'
                  }`}>{s.status}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
