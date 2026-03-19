// Map avg days to a 0–100% bar (cap at 120 days = 100%)
const MAX_DAYS = 120

export default function DurationGauge({ avgDays, casesWithDuration }) {
  const pct = Math.min((avgDays / MAX_DAYS) * 100, 100)

  return (
    <div className="stat-pill" style={{ minWidth: 220 }}>
      <span className="stat-pill__label">Avg Case Duration</span>
      <span className="stat-pill__value">{avgDays}d</span>
      <div style={{ height: 4, background: 'var(--border)', borderRadius: 2 }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: 'linear-gradient(90deg, var(--accent), #a78bfa)',
          borderRadius: 2,
        }} />
      </div>
      <span className="stat-pill__sub">across {casesWithDuration.toLocaleString()} cases with dates</span>
    </div>
  )
}
