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
          'parties, clerk administration, committee deliberation, and enforcement. ' +
          'Generated using Hugging Face BERT NER model for entity extraction.',
      },
      {
        id: 'arb-man-in-black',
        label: 'Wikipedia:Arbitration/Requests/Cases/A Man In Black',
        file: '/bpmn/arbitration/arb_Wikipedia_Arbitration_Requests_Case_A_Man_In_Black.bpmn',
        url: 'https://en.wikipedia.org/wiki/Wikipedia:Arbitration/Requests/Cases/A_Man_In_Black',
        description:
          'ArbCom case for A Man In Black dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement. ' +
          'Generated using Hugging Face BERT NER model for entity extraction.',
      },
      {
        id: 'arb-abd-jzg',
        label: 'Abd and JzG',
        file: '/bpmn/arbitration/arb_0002_Abd_and_JzG.bpmn',
        url: null,
        description:
          'ArbCom case for Abd and JzG dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'arb-article-titles',
        label: 'Article titles and capitalisation 2',
        file: '/bpmn/arbitration/arb_0003_Article_titles_and_capitalisation_2.bpmn',
        url: null,
        description:
          'ArbCom case for article titles and capitalisation dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'arb-man-in-black-alt',
        label: 'A Man In Black (alt)',
        file: '/bpmn/arbitration/arb_0001_A_Man_In_Black.bpmn',
        url: null,
        description:
          'ArbCom case for A Man In Black dispute (alternative). Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'arb-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/arbitration/arb_aggregate_workflow.bpmn',
        url: null,
        description:
          'Generalised BPMN workflow showing common process paths across all arbitration cases.',
      },
    ],
  },
  {
    id: 'rfc',
    label: 'RFC',
    cases: [
      {
        id: 'rfc-global-abusefilter',
        label: 'Global AbuseFilter',
        file: '/bpmn/rfc/rfc_0001_Global_AbuseFilter.bpmn',
        url: null,
        description:
          'RFC case for Global AbuseFilter. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'rfc-ongoing-chinese',
        label: 'Ongoing issues at Chinese Wikipedia',
        file: '/bpmn/rfc/rfc_0002_Ongoing_issues_at_Chinese_Wikipedia_-_Resorti.bpmn',
        url: null,
        description:
          'RFC case for ongoing issues at Chinese Wikipedia. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'rfc-turkish-wikipedia',
        label: 'Turkish Wikipedia copies again from Ansiklope',
        file: '/bpmn/rfc/rfc_0003_Turkish_wikipedia_copies_again_from_Ansiklope.bpmn',
        url: null,
        description:
          'RFC case for Turkish Wikipedia copying from Ansiklope. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'rfc-sysop-abuse',
        label: 'Sysop abuse on Wikiversité',
        file: '/bpmn/rfc/rfc_0004_Sysop_abuse_on_Wikiversité.bpmn',
        url: null,
        description:
          'RFC case for sysop abuse on Wikiversité. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'rfc-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/rfc/rfc_aggregate_workflow.bpmn',
        url: null,
        description:
          'Generalised BPMN workflow showing common process paths across all RFC cases.',
      },
    ],
  },
  {
    id: 'drn',
    label: 'DRN',
    cases: [
      {
        id: 'drn-adam-milstein',
        label: 'Adam Milstein',
        file: '/bpmn/drn/case_001_Adam_Milstein.bpmn',
        url: null,
        description:
          'DRN case for Adam Milstein dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-talk-touhou',
        label: 'Talk:Touhou Project',
        file: '/bpmn/drn/case_001_Talk_Touhou_Project.bpmn',
        url: null,
        description:
          'DRN case for Talk:Touhou Project dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-template-vermont',
        label: 'Template:Vermont',
        file: '/bpmn/drn/case_002_Template_Vermont.bpmn',
        url: null,
        description:
          'DRN case for Template:Vermont dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-occupy-wall-street',
        label: 'Occupy Wall Street',
        file: '/bpmn/drn/case_002_Occupy_Wall_Street.bpmn',
        url: null,
        description:
          'DRN case for Occupy Wall Street dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-george-v',
        label: 'George V',
        file: '/bpmn/drn/case_003_George_V.bpmn',
        url: null,
        description:
          'DRN case for George V dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-power-electronics',
        label: 'Power Electronics',
        file: '/bpmn/drn/case_003_Power_Electronics.bpmn',
        url: null,
        description:
          'DRN case for Power Electronics dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-speedy-deletion',
        label: 'Speedy deletion of page Gerardo Poggi',
        file: '/bpmn/drn/case_004_Speedy_deletion_of_page_Gerardo_Poggi.bpmn',
        url: null,
        description:
          'DRN case for speedy deletion of page Gerardo Poggi dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'drn-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/drn/drn_aggregate_workflow.bpmn',
        url: null,
        description:
          'Generalised BPMN workflow showing common process paths across all DRN cases.',
      },
    ],
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
