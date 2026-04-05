const TFS = ['1H', '4H', 'D', 'W']

export default function TimeframeSelector({ value, onChange }) {
  return (
    <div className="flex rounded-md border border-bg-border overflow-hidden">
      {TFS.map(tf => (
        <button
          key={tf}
          onClick={() => onChange(tf)}
          className={`px-3 py-1.5 text-sm font-medium transition-colors ${
            value === tf
              ? 'bg-brand text-white'
              : 'bg-bg-card text-text-secondary hover:bg-bg-hover hover:text-text-primary'
          }`}
        >
          {tf}
        </button>
      ))}
    </div>
  )
}
