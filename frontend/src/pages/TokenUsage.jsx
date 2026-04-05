import { useApi } from '../hooks/useApi'
import { ENDPOINTS } from '../utils/api'
import MetricCard from '../components/MetricCard'

function BudgetBar({ used, budget, label }) {
  const pct = Math.min((used / budget) * 100, 100)
  const color = pct >= 90 ? 'bg-short' : pct >= 70 ? 'bg-warn' : 'bg-long'
  return (
    <div>
      <div className="flex justify-between text-xs text-text-muted mb-1">
        <span>{label}</span>
        <span>${used.toFixed(4)} / ${budget.toFixed(2)}</span>
      </div>
      <div className="h-2 bg-bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-right text-xs text-text-muted mt-0.5">{pct.toFixed(1)}% used</p>
    </div>
  )
}

export default function TokenUsage() {
  const { data, loading, refetch } = useApi(ENDPOINTS.tokenUsage, { interval: 60000 })

  const budget = data?.budget
  const byAgent = data?.by_agent_today ?? {}

  const dailyAlert  = budget?.daily_exceeded
  const monthlyAlert = budget?.monthly_exceeded

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Token Usage</h1>
        <button onClick={refetch} className="btn-secondary text-xs">Refresh</button>
      </div>

      {(dailyAlert || monthlyAlert) && (
        <div className="bg-short/10 border border-short/30 text-short text-sm px-4 py-3 rounded-md">
          Budget exceeded: {[dailyAlert && 'daily', monthlyAlert && 'monthly'].filter(Boolean).join(' & ')} limit reached.
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Today's Cost" value={data ? `$${data.daily_cost_usd.toFixed(4)}` : '—'} loading={loading} color={dailyAlert ? 'text-short' : undefined} />
        <MetricCard label="This Week" value={data ? `$${data.weekly_cost_usd.toFixed(4)}` : '—'} loading={loading} />
        <MetricCard label="This Month" value={data ? `$${data.monthly_cost_usd.toFixed(4)}` : '—'} loading={loading} color={monthlyAlert ? 'text-short' : undefined} />
        <MetricCard label="Calls Today" value={data?.total_calls_today?.toString() ?? '—'} sub={`${data?.total_calls_month ?? '—'} this month`} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card space-y-4">
          <h2 className="font-medium text-text-primary">Budget Utilization</h2>
          {loading ? (
            <div className="space-y-4">{Array(2).fill(0).map((_, i) => <div key={i} className="skeleton h-10" />)}</div>
          ) : budget ? (
            <>
              <BudgetBar used={data.daily_cost_usd} budget={budget.daily_budget_usd} label="Daily Budget" />
              <BudgetBar used={data.monthly_cost_usd} budget={budget.monthly_budget_usd} label="Monthly Budget" />
            </>
          ) : <p className="text-text-muted text-sm">No data.</p>}
        </div>

        <div className="card">
          <h2 className="font-medium text-text-primary mb-3">By Agent (Today)</h2>
          {loading ? (
            <div className="space-y-2">{Array(3).fill(0).map((_, i) => <div key={i} className="skeleton h-8" />)}</div>
          ) : Object.keys(byAgent).length === 0 ? (
            <p className="text-text-muted text-sm">No API calls today yet.</p>
          ) : (
            <div className="space-y-2">
              {Object.entries(byAgent).map(([agent, cost]) => (
                <div key={agent} className="flex items-center justify-between text-sm py-1.5 border-b border-bg-border last:border-0">
                  <span className="text-text-secondary capitalize">{agent.replace('_', ' ')}</span>
                  <span className="font-mono text-text-primary">${cost.toFixed(4)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="font-medium text-text-primary mb-2">Projected Monthly Cost</h2>
        <p className="text-text-muted text-sm">Based on current usage rates with prompt caching:</p>
        <div className="grid grid-cols-3 gap-4 mt-3">
          {[
            { agent: 'Screener (Haiku)', proj: '~$0.35' },
            { agent: 'Analyst (Sonnet)', proj: '~$1.80' },
            { agent: 'News Sentinel (Haiku)', proj: '~$0.17' },
          ].map(r => (
            <div key={r.agent} className="bg-bg-secondary rounded-md px-3 py-2 text-sm">
              <p className="text-text-muted text-xs">{r.agent}</p>
              <p className="font-mono font-semibold text-text-primary mt-1">{r.proj}/mo</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-text-muted mt-3">Total projected: ~$2.30/month vs $20 budget (89% headroom)</p>
      </div>
    </div>
  )
}
