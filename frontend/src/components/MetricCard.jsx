export default function MetricCard({ label, value, sub, color, loading }) {
  return (
    <div className="card">
      <p className="label mb-1">{label}</p>
      {loading ? (
        <div className="skeleton h-7 w-24 mb-1" />
      ) : (
        <p className={`text-2xl font-bold ${color ?? 'text-text-primary'}`}>{value}</p>
      )}
      {sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}
    </div>
  )
}
