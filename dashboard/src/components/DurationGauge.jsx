import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
} from 'recharts'

// Map avg days to a 0-180 gauge (cap at 120 days = 100%)
const MAX_DAYS = 120

export default function DurationGauge({ avgDays, casesWithDuration }) {
  const pct = Math.min((avgDays / MAX_DAYS) * 100, 100)

  const chartData = [{ name: 'Duration', value: pct, fill: '#4f8ef7' }]

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div className="card__title" style={{ alignSelf: 'flex-start' }}>Average Case Duration</div>
      <div style={{ position: 'relative', width: 220, height: 130 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%" cy="100%"
            innerRadius="70%"
            outerRadius="100%"
            startAngle={180}
            endAngle={0}
            data={chartData}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar
              background={{ fill: '#2e3450' }}
              dataKey="value"
              cornerRadius={6}
            />
          </RadialBarChart>
        </ResponsiveContainer>
        {/* Center label */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          textAlign: 'center',
        }}>
          <div style={{
            fontSize: 30,
            fontWeight: 800,
            background: 'linear-gradient(135deg, #4f8ef7, #a78bfa)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
            {avgDays}d
          </div>
        </div>
      </div>
      <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 12, textAlign: 'center' }}>
        Average across {casesWithDuration.toLocaleString()} cases with parseable open/close dates.
        <br />Reference max: {MAX_DAYS} days.
      </p>
    </div>
  )
}
