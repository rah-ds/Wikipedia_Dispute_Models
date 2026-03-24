import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts'

// Bucket 0-based statement counts into readable bins
function bucketData(raw) {
  const buckets = {
    '0': 0, '1': 0, '2': 0, '3': 0, '4': 0,
    '5–9': 0, '10–19': 0, '20–34': 0, '35+': 0,
  }
  for (const { statementCount, cases } of raw) {
    const n = statementCount
    if (n === 0) buckets['0'] += cases
    else if (n === 1) buckets['1'] += cases
    else if (n === 2) buckets['2'] += cases
    else if (n === 3) buckets['3'] += cases
    else if (n === 4) buckets['4'] += cases
    else if (n <= 9)  buckets['5–9'] += cases
    else if (n <= 19) buckets['10–19'] += cases
    else if (n <= 34) buckets['20–34'] += cases
    else              buckets['35+'] += cases
  }
  return Object.entries(buckets).map(([name, cases]) => ({ name, cases }))
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="custom-tooltip">
      <div className="custom-tooltip__label">Statements: {label}</div>
      <div className="custom-tooltip__value">{payload[0].value} cases</div>
    </div>
  )
}

const COLORS = [
  '#4f8ef7', '#5d9cf8', '#6baaf9', '#79b8fa',
  '#87c6fb', '#95d4fc', '#a3e2fd', '#b1f0fe', '#bfffff',
]

export default function StatementDistChart({ data }) {
  const chartData = bucketData(data)

  return (
    <div className="card">
      <div className="card__title">Statements per Case — Distribution</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2e3450" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: '#8b92b8', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#8b92b8', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={36}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(79,142,247,0.08)' }} />
          <Bar dataKey="cases" radius={[4, 4, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
        Number of "Statement by" headers found in each arbitration page.
      </p>
    </div>
  )
}
