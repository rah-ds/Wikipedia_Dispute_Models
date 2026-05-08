import { useDashboardData } from '../hooks/useDashboardData'
import StatPills from '../components/StatPills'
import StatementDistChart from '../components/StatementDistChart'
import RemedyVerbsChart from '../components/RemedyVerbsChart'
import DurationGauge from '../components/DurationGauge'
import PartiesDonut from '../components/PartiesDonut'

export default function OverviewScreen() {
  const { data, loading, error } = useDashboardData()

  if (loading) return <LoadingState />
  if (error)   return <ErrorState message={error} />

  return (
    <div>
      <div className="screen-header">
        <h1>Arbitration Overview</h1>
        <p>
          Analysis of {data.totalCases.toLocaleString()} Wikipedia arbitration cases —
          text parsed from MediaWiki markup.
        </p>
      </div>

      {/* KPI row */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', alignItems: 'stretch' }}>
        <StatPills data={data} style={{ marginBottom: 0, flex: 1 }} />
        <DurationGauge
          avgDays={data.averageDurationDays}
          casesWithDuration={data.casesWithDuration}
        />
      </div>

      {/* Charts row */}
      <div className="chart-grid" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
        <StatementDistChart data={data.statementByDistribution} />
        <PartiesDonut data={data.casesPerYear} />
        <RemedyVerbsChart data={data.topRemedyVerbs} />
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: 400, flexDirection: 'column', gap: 12,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        border: '3px solid var(--border)',
        borderTopColor: 'var(--accent)',
        animation: 'spin 0.8s linear infinite',
      }} />
      <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Loading data…</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: 300,
    }}>
      <div className="card" style={{ textAlign: 'center', maxWidth: 400 }}>
        <div style={{ fontSize: 24, marginBottom: 8 }}>⚠️</div>
        <div style={{ color: 'var(--red)', fontWeight: 600 }}>Failed to load dashboard data</div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 6 }}>{message}</div>
      </div>
    </div>
  )
}
