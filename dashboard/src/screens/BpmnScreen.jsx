import { useState, lazy, Suspense, useEffect } from 'react'
import { Maximize2, X } from 'lucide-react'

const BpmnViewer = lazy(() => import('../components/BpmnViewer'))

const SECTIONS = [
  {
    id: 'arbitration',
    label: 'Arbitration Cases',
    cases: [
      {
        id: 'arb-ril',
        label: 'Wikipedia:Requests for arbitration/-Ril-',
        file: '/bpmn/arbitration/arb_Wikipedia_Requests_for_arbitration_-Ril-.bpmn',
        url: 'https://en.wikipedia.org/wiki/Wikipedia:Requests_for_arbitration/-Ril-',
        description:
          'ArbCom case for the -Ril- dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
    ],
  },
  {
    id: 'rfc',
    label: 'RFC',
    cases: [],
  },
  {
    id: 'drn',
    label: 'DRN',
    cases: [],
  },
]

function ViewerSuspense({ url }) {
  return (
    <Suspense fallback={
      <div style={{ color: 'var(--text-muted)', padding: 24 }}>Loading viewer…</div>
    }>
      <BpmnViewer key={url} url={url} />
    </Suspense>
  )
}

export default function BpmnScreen() {
  const [activeSection, setActiveSection] = useState(SECTIONS[0])
  const [selected, setSelected]           = useState(SECTIONS[0].cases[0] ?? null)
  const [expanded, setExpanded]           = useState(false)

  // Close overlay on Escape
  useEffect(() => {
    if (!expanded) return
    const handler = (e) => { if (e.key === 'Escape') setExpanded(false) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [expanded])

  const handleSection = (section) => {
    setActiveSection(section)
    setSelected(section.cases[0] ?? null)
    setExpanded(false)
  }

  return (
    <div className="bpmn-screen">
      {/* ── Top section header ── */}
      <div className="bpmn-section-header">
        <h1>Process Diagrams</h1>
        <nav className="bpmn-section-tabs">
          {SECTIONS.map(s => (
            <button
              key={s.id}
              className={`bpmn-section-tab${activeSection.id === s.id ? ' bpmn-section-tab--active' : ''}`}
              onClick={() => handleSection(s)}
            >
              {s.label}
              <span className="bpmn-section-tab__count">{s.cases.length}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* ── Body: left panel + viewer ── */}
      <div className="bpmn-body">
        {/* Left panel */}
        <aside className="bpmn-panel">
          <div className="bpmn-panel__title">Cases</div>
          {activeSection.cases.length === 0 ? (
            <div className="bpmn-panel__empty">
              No BPMN diagrams yet for {activeSection.label}.
            </div>
          ) : (
            activeSection.cases.map(c => (
              <button
                key={c.id}
                className={`bpmn-item${selected?.id === c.id ? ' bpmn-item--active' : ''}`}
                onClick={() => setSelected(c)}
              >
                {c.label}
              </button>
            ))
          )}
        </aside>

        {/* Inline viewer */}
        <div className="bpmn-viewer">
          {selected ? (
            <>
              <div className="bpmn-viewer__header">
                <div style={{ minWidth: 0 }}>
                  <h2>{selected.label}</h2>
                  <div className="bpmn-viewer__desc">{selected.description}</div>
                  {selected.url && (
                    <a
                      className="bpmn-viewer__link"
                      href={selected.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      View on Wikipedia ↗
                    </a>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span className="bpmn-badge">BPMN</span>
                  <button
                    className="bpmn-expand-btn"
                    onClick={() => setExpanded(true)}
                    title="Expand diagram"
                  >
                    <Maximize2 size={15} />
                  </button>
                </div>
              </div>
              <div className="bpmn-viewer__body bpmn-viewer__body--xml">
                <ViewerSuspense url={selected.file} />
              </div>
            </>
          ) : (
            <div className="bpmn-viewer__empty">
              <span>No diagrams in this section yet.</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Fullscreen overlay ── */}
      {expanded && selected && (
        <div className="bpmn-overlay" onClick={() => setExpanded(false)}>
          <div className="bpmn-overlay__panel" onClick={e => e.stopPropagation()}>
            <div className="bpmn-overlay__header">
              <span className="bpmn-overlay__title">{selected.label}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="bpmn-badge">BPMN</span>
                <button
                  className="bpmn-overlay__close"
                  onClick={() => setExpanded(false)}
                  title="Close (Esc)"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="bpmn-overlay__body">
              <ViewerSuspense url={selected.file} />
            </div>
            <div className="bpmn-overlay__hint">
              Press Esc or click outside to close
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
