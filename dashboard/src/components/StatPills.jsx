export default function StatPills({ data, style }) {
  const pills = [
    {
      label: 'Total Cases',
      value: data.totalCases.toLocaleString(),
      sub: 'arbitration proceedings',
    },
    {
      label: 'Unique User Links',
      value: data.totalUserLinks.toLocaleString(),
      sub: 'distinct [[User:…]] mentions',
    },
    {
      label: 'Admin Talk Links',
      value: data.totalAdminLinks.toLocaleString(),
      sub: 'distinct [[User talk:…]] mentions',
    },
  ]

  return (
    <div className="stat-pills" style={style}>
      {pills.map(p => (
        <div key={p.label} className="stat-pill">
          <span className="stat-pill__label">{p.label}</span>
          <span className="stat-pill__value">{p.value}</span>
          <span className="stat-pill__sub">{p.sub}</span>
        </div>
      ))}
    </div>
  )
}
