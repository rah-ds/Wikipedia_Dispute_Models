import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LabelList,
} from 'recharts'

const GRADIENT_COLORS = [
  '#e05d6a', '#e06b5d', '#e07950', '#e08743',
  '#e09536', '#c99530', '#b3952a', '#9d9524',
  '#87951e', '#719518', '#5b9512', '#45950c',
  '#2f9506', '#199500', '#03950a',
]

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="custom-tooltip">
      <div className="custom-tooltip__label">Verb: <strong style={{ color: 'var(--text)' }}>{label}</strong></div>
      <div className="custom-tooltip__value">{payload[0].value.toLocaleString()} occurrences</div>
    </div>
  )
}

export default function RemedyVerbsChart({ data }) {
  // data is already sorted descending from the Python script
  const top12 = data.slice(0, 12)

  return (
    <div className="card">
      <div className="card__title">Top Remedy Action Verbs</div>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart
          data={top12}
          layout="vertical"
          margin={{ top: 4, right: 48, bottom: 4, left: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#2e3450" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: '#8b92b8', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="verb"
            width={88}
            tick={{ fill: '#e8eaf6', fontSize: 13, fontWeight: 500 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(79,142,247,0.08)' }} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            <LabelList
              dataKey="count"
              position="right"
              style={{ fill: '#8b92b8', fontSize: 12 }}
            />
            {top12.map((_, i) => (
              <Cell key={i} fill={GRADIENT_COLORS[i % GRADIENT_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
        Action verbs extracted from Remedies sections only (stop-words excluded).
      </p>
    </div>
  )
}
