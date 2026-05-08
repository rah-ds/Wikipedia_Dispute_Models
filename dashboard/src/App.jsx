import { useState } from 'react'
import OverviewScreen from './screens/OverviewScreen'
import BpmnScreen from './screens/BpmnScreen'
import D3Screen from './screens/D3Screen'
import './App.css'

const TABS = [
  { id: 'overview', label: 'Arbitration Overview' },
  { id: 'd3', label: 'D3 Visuals' },
  { id: 'bpmn', label: 'Process Diagrams' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('overview')

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <div className="app-header__brand">
            <span className="brand-dot" />
            <span className="brand-title">Wikipedia Dispute Arbitration Overview</span>
          </div>
          <nav className="tab-nav">
            {TABS.map(t => (
              <button
                key={t.id}
                className={`tab-btn${activeTab === t.id ? ' tab-btn--active' : ''}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="app-main">
        {activeTab === 'overview' && <OverviewScreen />}
        {activeTab === 'd3'       && <D3Screen />}
        {activeTab === 'bpmn'     && <BpmnScreen />}
      </main>
    </div>
  )
}
