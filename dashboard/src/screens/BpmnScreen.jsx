import { useState, lazy, Suspense, useEffect } from 'react'
import { Maximize2, X } from 'lucide-react'

const BpmnViewer = lazy(() => import('../components/BpmnViewer'))

const SECTIONS = [
  {
    id: 'arbitration',
    label: 'Arbitration Cases',
    cases: [
      {
        id: 'arb-0001-ril',
        label: 'Arbitration Case 1 - -Ril-',
        file: '/bpmn/arb/arb_0001_-Ril-.bpmn',
        url: null,
        description: 'Arbitration case for the -Ril- dispute.',
      },
      {
        id: 'arb-0002-8bitjake',
        label: 'Arbitration Case 2 - 8bitJake',
        file: '/bpmn/arb/arb_0002_8bitJake.bpmn',
        url: null,
        description: 'Arbitration case for 8bitJake dispute.',
      },
      {
        id: 'arb-0003-168',
        label: 'Arbitration Case 3 - 168/209/97/34',
        file: '/bpmn/arb/arb_0003_168_209_97_34.bpmn',
        url: null,
        description: 'Arbitration case involving editors 168, 209, 97, 34.',
      },
      {
        id: 'arb-0004-172',
        label: 'Arbitration Case 4 - 172',
        file: '/bpmn/arb/arb_0004_172.bpmn',
        url: null,
        description: 'Arbitration case for editor 172.',
      },
      {
        id: 'arb-0005-172-2',
        label: 'Arbitration Case 5 - 172 (2)',
        file: '/bpmn/arb/arb_0005_172_2.bpmn',
        url: null,
        description: 'Second arbitration case for editor 172.',
      },
      {
        id: 'arb-0006-194',
        label: 'Arbitration Case 6 - 194x144x90x118',
        file: '/bpmn/arb/arb_0006_194x144x90x118.bpmn',
        url: null,
        description: 'Arbitration case involving multiple editors.',
      },
      {
        id: 'arb-0007-man-in-black',
        label: 'Arbitration Case 7 - A Man In Black',
        file: '/bpmn/arb/arb_0007_A_Man_In_Black.bpmn',
        url: null,
        description: 'Arbitration case for A Man In Black dispute.',
      },
      {
        id: 'arb-man-in-black-wikipedia',
        label: 'Arbitration Case 7 - A Man In Black (HuggingFace XML)',
        file: '/bpmn/arb/arb_Wikipedia_Arbitration_Requests_Case_A_Man_In_Black.bpmn',
        url: 'https://en.wikipedia.org/wiki/Wikipedia:Arbitration/Requests/Cases/A_Man_In_Black',
        description:
          'Arbitration case for A Man In Black dispute, generated with the Hugging Face XML pipeline. ' +
          'Swimlane model covering involved parties, clerk administration, committee deliberation, and enforcement.',
      },
      {
        id: 'arb-0008-nobody',
        label: 'Arbitration Case 8 - A Nobody',
        file: '/bpmn/arb/arb_0008_A_Nobody.bpmn',
        url: null,
        description: 'Arbitration case for A Nobody dispute.',
      },
      {
        id: 'arb-0009-abd-jzg',
        label: 'Arbitration Case 9 - Abd and JzG',
        file: '/bpmn/arb/arb_0009_Abd_and_JzG.bpmn',
        url: null,
        description: 'Arbitration case for Abd and JzG dispute.',
      },
      {
        id: 'arb-0010-abortion',
        label: 'Arbitration Case 10 - Abortion',
        file: '/bpmn/arb/arb_0010_Abortion.bpmn',
        url: null,
        description: 'Arbitration case for Abortion article dispute.',
      },
      {
        id: 'arb-ril-wikipedia',
        label: 'Wikipedia:Requests for arbitration/-Ril-',
        file: '/bpmn/arb/arb_Wikipedia_Requests_for_arbitration_-Ril-.bpmn',
        url: 'https://en.wikipedia.org/wiki/Wikipedia:Requests_for_arbitration/-Ril-',
        description:
          'ArbCom case for the -Ril- dispute. Swimlane model covering involved ' +
          'parties, clerk administration, committee deliberation, and enforcement. ' +
          'Generated using Hugging Face BERT NER model for entity extraction.',
      },
      {
        id: 'arb-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/arbitration/arb_aggregate_workflow.bpmn',
        url: '/bpmn/arbitration/arb_aggregate_workflow.bpmn',
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
        description: 'RFC case for Global AbuseFilter.',
      },
      {
        id: 'rfc-anais-azerbaijan',
        label: 'Anais article with abusive content (Azerbaijan)',
        file: '/bpmn/rfc/rfc_0001_Anais_article_with_abusive_content_in_Azerbai.bpmn',
        url: null,
        description: 'RFC case for Anais article with abusive content in Azerbaijan.',
      },
      {
        id: 'rfc-ongoing-chinese',
        label: 'Ongoing issues at Chinese Wikipedia',
        file: '/bpmn/rfc/rfc_0002_Ongoing_issues_at_Chinese_Wikipedia_-_Resorti.bpmn',
        url: null,
        description: 'RFC case for ongoing issues at Chinese Wikipedia.',
      },
      {
        id: 'rfc-from-wikipedia',
        label: 'From Wikipedia the free encyclopedia incomplete',
        file: '/bpmn/rfc/rfc_0002_From_Wikipedia_the_free_encyclopedia_incomple.bpmn',
        url: null,
        description: 'RFC case for incomplete "From Wikipedia the free encyclopedia" text.',
      },
      {
        id: 'rfc-turkish-wikipedia',
        label: 'Turkish Wikipedia copies again from Ansiklope',
        file: '/bpmn/rfc/rfc_0003_Turkish_wikipedia_copies_again_from_Ansiklope.bpmn',
        url: null,
        description: 'RFC case for Turkish Wikipedia copying from Ansiklope.',
      },
      {
        id: 'rfc-putin-khuylo',
        label: 'Putin khuylo on the main page',
        file: '/bpmn/rfc/rfc_0003_Putin_khuylo_on_the_main_page.bpmn',
        url: null,
        description: 'RFC case for Putin khuylo on the main page.',
      },
      {
        id: 'rfc-sysop-abuse',
        label: 'Sysop abuse on Wikiversité',
        file: '/bpmn/rfc/rfc_0004_Sysop_abuse_on_Wikiversité.bpmn',
        url: null,
        description: 'RFC case for sysop abuse on Wikiversité.',
      },
      {
        id: 'rfc-simpsons-hebrew',
        label: 'Simpsons Roasting on an Open Fire (Hebrew Wikipedia)',
        file: '/bpmn/rfc/rfc_0004_Simpsons_Roasting_on_an_Open_Fire_on_Hebrew_W.bpmn',
        url: null,
        description: 'RFC case for Simpsons episode on Hebrew Wikipedia.',
      },
      {
        id: 'rfc-adminship',
        label: 'What adminship is not',
        file: '/bpmn/rfc/rfc_0005_What_adminship_is_not_does_not_work_in_the_Po.bpmn',
        url: null,
        description: 'RFC case for adminship scope and definition.',
      },
      {
        id: 'rfc-jkb',
        label: '-jkb- case',
        file: '/bpmn/rfc/rfc_0006_-jkb-.bpmn',
        url: null,
        description: 'RFC case involving -jkb-.',
      },
      {
        id: 'rfc-croatian-wikipedia',
        label: '2013 issues on Croatian Wikipedia',
        file: '/bpmn/rfc/rfc_0007_2013_issues_on_Croatian_Wikipedia.bpmn',
        url: null,
        description: 'RFC case for 2013 issues on Croatian Wikipedia.',
      },
      {
        id: 'rfc-bureaucrat-troll',
        label: 'A bureaucrat which supports a troll (Hebrew)',
        file: '/bpmn/rfc/rfc_0008_A_bureaucrat_which_supports_a_troll_in_the_He.bpmn',
        url: null,
        description: 'RFC case for bureaucrat supporting troll on Hebrew Wikipedia.',
      },
      {
        id: 'rfc-global-lock',
        label: 'A new global lock reason',
        file: '/bpmn/rfc/rfc_0009_A_new_global_lock_reason.bpmn',
        url: null,
        description: 'RFC case for new global lock reason.',
      },
      {
        id: 'rfc-abandoned-labs',
        label: 'Abandoned Labs tools',
        file: '/bpmn/rfc/rfc_0010_Abandoned_Labs_tools.bpmn',
        url: null,
        description: 'RFC case for abandoned tools on Labs.',
      },
      {
        id: 'rfc-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/rfc/rfc_aggregate_workflow.bpmn',
        url: null,
        description: 'Generalised BPMN workflow showing common process paths across all RFC cases.',
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
        description: 'DRN case for Adam Milstein dispute.',
      },
      {
        id: 'drn-talk-touhou',
        label: 'Talk:Touhou Project',
        file: '/bpmn/drn/case_001_Talk_Touhou_Project.bpmn',
        url: null,
        description: 'DRN case for Talk:Touhou Project dispute.',
      },
      {
        id: 'drn-template-vermont',
        label: 'Template:Vermont',
        file: '/bpmn/drn/case_002_Template_Vermont.bpmn',
        url: null,
        description: 'DRN case for Template:Vermont dispute.',
      },
      {
        id: 'drn-occupy-wall-street',
        label: 'Occupy Wall Street',
        file: '/bpmn/drn/case_002_Occupy_Wall_Street.bpmn',
        url: null,
        description: 'DRN case for Occupy Wall Street dispute.',
      },
      {
        id: 'drn-george-v',
        label: 'George V',
        file: '/bpmn/drn/case_003_George_V.bpmn',
        url: null,
        description: 'DRN case for George V dispute.',
      },
      {
        id: 'drn-power-electronics',
        label: 'Power Electronics',
        file: '/bpmn/drn/case_003_Power_Electronics.bpmn',
        url: null,
        description: 'DRN case for Power Electronics dispute.',
      },
      {
        id: 'drn-speedy-deletion',
        label: 'Speedy deletion of page Gerardo Poggi',
        file: '/bpmn/drn/case_004_Speedy_deletion_of_page_Gerardo_Poggi.bpmn',
        url: null,
        description: 'DRN case for speedy deletion of page Gerardo Poggi.',
      },
      {
        id: 'drn-culpeper',
        label: 'Culpeper',
        file: '/bpmn/drn/case_004_Culpeper.bpmn',
        url: null,
        description: 'DRN case for Culpeper dispute.',
      },
      {
        id: 'drn-lackawanna-cutoff',
        label: 'Lackawanna Cut-Off',
        file: '/bpmn/drn/case_005_Lackawanna_Cut-Off.bpmn',
        url: null,
        description: 'DRN case for Lackawanna Cut-Off dispute.',
      },
      {
        id: 'drn-speed-limit',
        label: 'Speed limit enforcement',
        file: '/bpmn/drn/case_006_Speed_limit_enforcement.bpmn',
        url: null,
        description: 'DRN case for speed limit enforcement.',
      },
      {
        id: 'drn-hinduism',
        label: 'Hinduism',
        file: '/bpmn/drn/case_007_Hinduism.bpmn',
        url: null,
        description: 'DRN case for Hinduism article dispute.',
      },
      {
        id: 'drn-mercedes',
        label: 'Mercedes-Benz article omits car components',
        file: '/bpmn/drn/case_008_Mercedes-Benz_article_omits_the_car_comp.bpmn',
        url: null,
        description: 'DRN case for Mercedes-Benz article omissions.',
      },
      {
        id: 'drn-homeopathy',
        label: 'Homeopathy - mention summary or description',
        file: '/bpmn/drn/case_009_Homeopathy_-_to_mention_a_summary_or_the.bpmn',
        url: null,
        description: 'DRN case for Homeopathy article description.',
      },
      {
        id: 'drn-chinaman',
        label: 'Chinaman term - whether to include information',
        file: '/bpmn/drn/case_010_Chinaman_term_-_whether_to_include_infor.bpmn',
        url: null,
        description: 'DRN case for Chinaman term usage.',
      },
      {
        id: 'drn-aggregate',
        label: 'Aggregate Workflow',
        file: '/bpmn/drn/drn_aggregate_workflow.bpmn',
        url: null,
        description: 'Generalised BPMN workflow showing common process paths across all DRN cases.',
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
                      {selected.url.startsWith('/bpmn/')
                        ? 'Open BPMN file ↗'
                        : 'View on Wikipedia ↗'}
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
