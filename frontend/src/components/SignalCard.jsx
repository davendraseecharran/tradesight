import { useState } from 'react'
import { fmtPrice, fmtTimeAgo, fmtPair, pairDecimals } from '../utils/formatters'
import { ENDPOINTS, apiFetch } from '../utils/api'

function ConfidenceMeter({ score }) {
  const pct = (score / 10) * 100
  const color = score >= 8 ? 'bg-long' : score >= 6 ? 'bg-brand' : 'bg-warn'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-text-muted w-8 text-right">{score}/10</span>
    </div>
  )
}

function ConfirmModal({ signal, action, onConfirm, onCancel }) {
  const isApprove = action === 'approve'
  const d = pairDecimals(signal.instrument)

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onCancel}>
      <div className="bg-bg-card border border-bg-border rounded-lg p-5 max-w-md w-full space-y-4" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold text-text-primary text-lg">
          {isApprove ? 'Confirm Trade Execution' : 'Reject Signal'}
        </h3>

        {isApprove ? (
          <div className="space-y-3">
            <p className="text-sm text-text-secondary">
              Execute this trade on your OANDA practice account?
            </p>
            <div className="bg-bg-primary/50 rounded-md p-3 space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-text-muted">Pair</span>
                <span className="font-mono font-medium">{fmtPair(signal.instrument)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Direction</span>
                <span className={signal.direction === 'long' ? 'text-long font-medium' : 'text-short font-medium'}>
                  {signal.direction?.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Entry</span>
                <span className="font-mono">{fmtPrice(signal.entry_price, d)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Stop Loss</span>
                <span className="font-mono text-short">{fmtPrice(signal.stop_loss, d)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Take Profit</span>
                <span className="font-mono text-long">{fmtPrice(signal.take_profit_1, d)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Position Size</span>
                <span className="font-mono">{signal.position_size ?? 0.01} lots</span>
              </div>
              {signal.risk_amount && (
                <div className="flex justify-between">
                  <span className="text-text-muted">Risk</span>
                  <span className="font-mono text-warn">${signal.risk_amount.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-text-secondary">
            Reject this signal? It won't be executed.
          </p>
        )}

        <div className="flex gap-3 pt-2">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 text-sm rounded-md border border-bg-border text-text-secondary hover:bg-bg-border transition"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 px-4 py-2 text-sm rounded-md font-medium transition ${
              isApprove
                ? 'bg-long text-white hover:bg-long/80'
                : 'bg-short text-white hover:bg-short/80'
            }`}
          >
            {isApprove ? 'Execute Trade' : 'Reject Signal'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ExecutionBadge({ status }) {
  if (!status) return null
  const styles = {
    pending_approval: 'bg-warn/10 text-warn',
    approved: 'bg-brand/10 text-brand',
    executed: 'bg-long/10 text-long',
    rejected: 'bg-short/10 text-short',
  }
  const labels = {
    pending_approval: 'Pending',
    approved: 'Approved',
    executed: 'Executed',
    rejected: 'Rejected',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${styles[status] || 'bg-bg-border text-text-muted'}`}>
      {labels[status] || status}
    </span>
  )
}

export default function SignalCard({ signal, compact = false, onAction }) {
  const [modal, setModal] = useState(null) // 'approve' | 'reject' | null
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const d = pairDecimals(signal.instrument)
  const isLong = signal.direction === 'long'

  const canAct = signal.execution_status === 'pending_approval'

  async function handleConfirm() {
    setLoading(true)
    setError(null)
    try {
      const url = modal === 'approve'
        ? ENDPOINTS.approveSignal(signal.id)
        : ENDPOINTS.rejectSignal(signal.id)
      await apiFetch(url, { method: 'POST' })
      setModal(null)
      if (onAction) onAction()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-primary">{fmtPair(signal.instrument)}</span>
            <span className={isLong ? 'badge-long' : 'badge-short'}>
              {isLong ? '▲ LONG' : '▼ SHORT'}
            </span>
            <ExecutionBadge status={signal.execution_status} />
            {!signal.risk_approved && (
              <span className="text-xs text-warn bg-warn/10 px-2 py-0.5 rounded">Risk Flagged</span>
            )}
            {signal.is_news_blackout && (
              <span className="text-xs text-short bg-short/10 px-2 py-0.5 rounded">News Blackout</span>
            )}
          </div>
          <span className="text-xs text-text-muted">{fmtTimeAgo(signal.created_at)}</span>
        </div>

        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="label">Entry</p>
            <p className="value font-mono">{fmtPrice(signal.entry_price, d)}</p>
          </div>
          <div>
            <p className="label">Stop Loss</p>
            <p className="value font-mono text-short">{fmtPrice(signal.stop_loss, d)}</p>
          </div>
          <div>
            <p className="label">Take Profit</p>
            <p className="value font-mono text-long">{fmtPrice(signal.take_profit_1, d)}</p>
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="label">Confidence</p>
            {signal.risk_reward_ratio && (
              <p className="text-xs text-text-muted">R:R 1:{signal.risk_reward_ratio?.toFixed(1)}</p>
            )}
          </div>
          <ConfidenceMeter score={signal.confidence} />
        </div>

        {!compact && signal.reasoning && (
          <div className="pt-2 border-t border-bg-border">
            <p className="label mb-1">Analysis</p>
            <p className="text-xs text-text-secondary leading-relaxed line-clamp-4">
              {signal.reasoning}
            </p>
          </div>
        )}

        {!compact && signal.rejection_reasons?.length > 0 && (
          <div className="bg-short/5 border border-short/20 rounded-md p-2">
            <p className="label text-short mb-1">Risk Flags</p>
            {signal.rejection_reasons.map((r, i) => (
              <p key={i} className="text-xs text-short">• {r}</p>
            ))}
          </div>
        )}

        {/* Approve / Reject buttons for SEMI_AUTO mode */}
        {canAct && !compact && (
          <div className="flex gap-2 pt-2 border-t border-bg-border">
            <button
              onClick={() => setModal('approve')}
              className="flex-1 px-3 py-1.5 text-sm font-medium rounded-md bg-long text-white hover:bg-long/80 transition"
            >
              Approve & Execute
            </button>
            <button
              onClick={() => setModal('reject')}
              className="flex-1 px-3 py-1.5 text-sm font-medium rounded-md bg-short/20 text-short hover:bg-short/30 transition"
            >
              Reject
            </button>
          </div>
        )}

        {error && (
          <p className="text-xs text-short">{error}</p>
        )}
      </div>

      {modal && (
        <ConfirmModal
          signal={signal}
          action={modal}
          onConfirm={handleConfirm}
          onCancel={() => { setModal(null); setError(null) }}
        />
      )}
    </>
  )
}
