import { useState, lazy, Suspense, useEffect } from 'react'
import { Maximize2, X } from 'lucide-react'

const BpmnViewer = lazy(() => import('../components/BpmnViewer'))

// ── Helpers ───────────────────────────────────────────────────────────────────

const pngFrom = (bpmnPath) => bpmnPath.replace('.bpmn', '.png')

function stemFromFile(filePath) {
  return filePath.split('/').pop().replace('.bpmn', '')
}

// ── Case definitions ──────────────────────────────────────────────────────────
//
// variants: array of { variantLabel?, file, url? }
//   - Single-variant cases: one entry, variantLabel omitted
//   - Multi-variant cases (7, 10): three entries with variantLabel shown as sub-headers
//
// File stem conventions:
//   arb_00*                               → Rules-Based Extraction
//   arb_Wikipedia_Arbitration_Requests_*  → HuggingFace BERT XML
//   arb_gemma_* / Wikipedia_Arbitration_* → Gemma Model XML

const SECTIONS = [
  {
    id: 'arbitration',
    label: 'Arbitration Cases',
    cases: [
      {
        id: 'arb-0001-ril',
        label: 'Arbitration Case 1 - -Ril-',
        description: 'Arbitration case for the -Ril- dispute.',
        variants: [{ file: '/bpmn/arb/arb_0001_-Ril-.bpmn' }],
      },
      {
        id: 'arb-0002-8bitjake',
        label: 'Arbitration Case 2 - 8bitJake',
        description: 'Arbitration case for 8bitJake dispute.',
        variants: [{ file: '/bpmn/arb/arb_0002_8bitJake.bpmn' }],
      },
      {
        id: 'arb-0003-168',
        label: 'Arbitration Case 3 - 168/209/97/34',
        description: 'Arbitration case involving editors 168, 209, 97, 34.',
        variants: [{ file: '/bpmn/arb/arb_0003_168_209_97_34.bpmn' }],
      },
      {
        id: 'arb-0004-172',
        label: 'Arbitration Case 4 - 172',
        description: 'Arbitration case for editor 172.',
        variants: [{ file: '/bpmn/arb/arb_0004_172.bpmn' }],
      },
      {
        id: 'arb-0005-172-2',
        label: 'Arbitration Case 5 - 172 (2)',
        description: 'Second arbitration case for editor 172.',
        variants: [{ file: '/bpmn/arb/arb_0005_172_2.bpmn' }],
      },
      {
        id: 'arb-0006-194',
        label: 'Arbitration Case 6 - 194x144x90x118',
        description: 'Arbitration case involving multiple editors.',
        variants: [{ file: '/bpmn/arb/arb_0006_194x144x90x118.bpmn' }],
      },
      {
        id: 'arb-0007-man-in-black',
        label: 'Arbitration Case 7 - A Man In Black',
        description: 'Three extraction methods compared: rules-based regex, HuggingFace BERT NER, and Gemma LLM. Scroll to view all.',
        variants: [
          {
            variantLabel: 'Rules-Based Extraction',
            file: '/bpmn/arb/arb_0007_A_Man_In_Black.bpmn',
          },
          {
            variantLabel: 'HuggingFace BERT XML',
            file: '/bpmn/arb/arb_Wikipedia_Arbitration_Requests_Case_A_Man_In_Black.bpmn',
            url: 'https://en.wikipedia.org/wiki/Wikipedia:Arbitration/Requests/Cases/A_Man_In_Black',
          },
          {
            variantLabel: 'Gemma Model XML',
            file: '/bpmn/arb/arb_gemma_A_Man_In_Black.bpmn',
          },
        ],
      },
      {
        id: 'arb-0008-nobody',
        label: 'Arbitration Case 8 - A Nobody',
        description: 'Arbitration case for A Nobody dispute.',
        variants: [{ file: '/bpmn/arb/arb_0008_A_Nobody.bpmn' }],
      },
      {
        id: 'arb-0009-abd-jzg',
        label: 'Arbitration Case 9 - Abd and JzG',
        description: 'Arbitration case for Abd and JzG dispute.',
        variants: [{ file: '/bpmn/arb/arb_0009_Abd_and_JzG.bpmn' }],
      },
      {
        id: 'arb-0010-abortion',
        label: 'Arbitration Case 10 - Abortion',
        description: 'Three extraction methods compared: rules-based regex, HuggingFace BERT NER, and Gemma LLM. Scroll to view all.',
        variants: [
          {
            variantLabel: 'Rules-Based Extraction',
            file: '/bpmn/arb/arb_0010_Abortion.bpmn',
          },
          {
            variantLabel: 'HuggingFace BERT XML',
            file: '/bpmn/arb/arb_Wikipedia_Arbitration_Requests_Case_Abortion.bpmn',
            url: 'https://en.wikipedia.org/wiki/Wikipedia:Arbitration/Requests/Cases/Abortion',
          },
          {
            variantLabel: 'Gemma Model XML',
            file: '/bpmn/arb/arb_gemma_Abortion.bpmn',
          },
        ],
      },
      {
        id: 'arb-ril-wikipedia',
        label: 'Wikipedia:Requests for arbitration/-Ril-',
        description: 'ArbCom case for the -Ril- dispute. Generated using Hugging Face BERT NER model for entity extraction.',
        variants: [{
          file: '/bpmn/arb/arb_Wikipedia_Requests_for_arbitration_-Ril-.bpmn',
          url: 'https://en.wikipedia.org/wiki/Wikipedia:Requests_for_arbitration/-Ril-',
        }],
      },
      {
        id: 'arb-aggregate',
        label: 'Aggregate Workflow',
        description: 'Generalised BPMN workflow showing common process paths across all arbitration cases.',
        variants: [{ file: '/bpmn/arbitration/arb_aggregate_workflow.bpmn' }],
      },
    ],
  },
  {
    id: 'rfc',
    label: 'RFC',
    cases: [
      { id: 'rfc-global-abusefilter', label: 'Global AbuseFilter', description: 'RFC case for Global AbuseFilter.', variants: [{ file: '/bpmn/rfc/rfc_0001_Global_AbuseFilter.bpmn' }] },
      { id: 'rfc-anais-azerbaijan', label: 'Anais article with abusive content (Azerbaijan)', description: 'RFC case for Anais article with abusive content in Azerbaijan.', variants: [{ file: '/bpmn/rfc/rfc_0001_Anais_article_with_abusive_content_in_Azerbai.bpmn' }] },
      { id: 'rfc-ongoing-chinese', label: 'Ongoing issues at Chinese Wikipedia', description: 'RFC case for ongoing issues at Chinese Wikipedia.', variants: [{ file: '/bpmn/rfc/rfc_0002_Ongoing_issues_at_Chinese_Wikipedia_-_Resorti.bpmn' }] },
      { id: 'rfc-from-wikipedia', label: 'From Wikipedia the free encyclopedia incomplete', description: 'RFC case for incomplete "From Wikipedia the free encyclopedia" text.', variants: [{ file: '/bpmn/rfc/rfc_0002_From_Wikipedia_the_free_encyclopedia_incomple.bpmn' }] },
      { id: 'rfc-turkish-wikipedia', label: 'Turkish Wikipedia copies again from Ansiklope', description: 'RFC case for Turkish Wikipedia copying from Ansiklope.', variants: [{ file: '/bpmn/rfc/rfc_0003_Turkish_wikipedia_copies_again_from_Ansiklope.bpmn' }] },
      { id: 'rfc-putin-khuylo', label: 'Putin khuylo on the main page', description: 'RFC case for Putin khuylo on the main page.', variants: [{ file: '/bpmn/rfc/rfc_0003_Putin_khuylo_on_the_main_page.bpmn' }] },
      { id: 'rfc-sysop-abuse', label: 'Sysop abuse on Wikiversité', description: 'RFC case for sysop abuse on Wikiversité.', variants: [{ file: '/bpmn/rfc/rfc_0004_Sysop_abuse_on_Wikiversité.bpmn' }] },
      { id: 'rfc-simpsons-hebrew', label: 'Simpsons Roasting on an Open Fire (Hebrew Wikipedia)', description: 'RFC case for Simpsons episode on Hebrew Wikipedia.', variants: [{ file: '/bpmn/rfc/rfc_0004_Simpsons_Roasting_on_an_Open_Fire_on_Hebrew_W.bpmn' }] },
      { id: 'rfc-adminship', label: 'What adminship is not', description: 'RFC case for adminship scope and definition.', variants: [{ file: '/bpmn/rfc/rfc_0005_What_adminship_is_not_does_not_work_in_the_Po.bpmn' }] },
      { id: 'rfc-jkb', label: '-jkb- case', description: 'RFC case involving -jkb-.', variants: [{ file: '/bpmn/rfc/rfc_0006_-jkb-.bpmn' }] },
      { id: 'rfc-croatian-wikipedia', label: '2013 issues on Croatian Wikipedia', description: 'RFC case for 2013 issues on Croatian Wikipedia.', variants: [{ file: '/bpmn/rfc/rfc_0007_2013_issues_on_Croatian_Wikipedia.bpmn' }] },
      { id: 'rfc-bureaucrat-troll', label: 'A bureaucrat which supports a troll (Hebrew)', description: 'RFC case for bureaucrat supporting troll on Hebrew Wikipedia.', variants: [{ file: '/bpmn/rfc/rfc_0008_A_bureaucrat_which_supports_a_troll_in_the_He.bpmn' }] },
      { id: 'rfc-global-lock', label: 'A new global lock reason', description: 'RFC case for new global lock reason.', variants: [{ file: '/bpmn/rfc/rfc_0009_A_new_global_lock_reason.bpmn' }] },
      { id: 'rfc-abandoned-labs', label: 'Abandoned Labs tools', description: 'RFC case for abandoned tools on Labs.', variants: [{ file: '/bpmn/rfc/rfc_0010_Abandoned_Labs_tools.bpmn' }] },
      { id: 'rfc-aggregate', label: 'Aggregate Workflow', description: 'Generalised BPMN workflow showing common process paths across all RFC cases.', variants: [{ file: '/bpmn/rfc/rfc_aggregate_workflow.bpmn' }] },
    ],
  },
  {
    id: 'drn',
    label: 'DRN',
    cases: [
      { id: 'drn-adam-milstein', label: 'Adam Milstein', description: 'DRN case for Adam Milstein dispute.', variants: [{ file: '/bpmn/drn/case_001_Adam_Milstein.bpmn' }] },
      { id: 'drn-talk-touhou', label: 'Talk:Touhou Project', description: 'DRN case for Talk:Touhou Project dispute.', variants: [{ file: '/bpmn/drn/case_001_Talk_Touhou_Project.bpmn' }] },
      { id: 'drn-template-vermont', label: 'Template:Vermont', description: 'DRN case for Template:Vermont dispute.', variants: [{ file: '/bpmn/drn/case_002_Template_Vermont.bpmn' }] },
      { id: 'drn-occupy-wall-street', label: 'Occupy Wall Street', description: 'DRN case for Occupy Wall Street dispute.', variants: [{ file: '/bpmn/drn/case_002_Occupy_Wall_Street.bpmn' }] },
      { id: 'drn-george-v', label: 'George V', description: 'DRN case for George V dispute.', variants: [{ file: '/bpmn/drn/case_003_George_V.bpmn' }] },
      { id: 'drn-power-electronics', label: 'Power Electronics', description: 'DRN case for Power Electronics dispute.', variants: [{ file: '/bpmn/drn/case_003_Power_Electronics.bpmn' }] },
      { id: 'drn-speedy-deletion', label: 'Speedy deletion of page Gerardo Poggi', description: 'DRN case for speedy deletion of page Gerardo Poggi.', variants: [{ file: '/bpmn/drn/case_004_Speedy_deletion_of_page_Gerardo_Poggi.bpmn' }] },
      { id: 'drn-culpeper', label: 'Culpeper', description: 'DRN case for Culpeper dispute.', variants: [{ file: '/bpmn/drn/case_004_Culpeper.bpmn' }] },
      { id: 'drn-lackawanna-cutoff', label: 'Lackawanna Cut-Off', description: 'DRN case for Lackawanna Cut-Off dispute.', variants: [{ file: '/bpmn/drn/case_005_Lackawanna_Cut-Off.bpmn' }] },
      { id: 'drn-speed-limit', label: 'Speed limit enforcement', description: 'DRN case for speed limit enforcement.', variants: [{ file: '/bpmn/drn/case_006_Speed_limit_enforcement.bpmn' }] },
      { id: 'drn-hinduism', label: 'Hinduism', description: 'DRN case for Hinduism article dispute.', variants: [{ file: '/bpmn/drn/case_007_Hinduism.bpmn' }] },
      { id: 'drn-mercedes', label: 'Mercedes-Benz article omits car components', description: 'DRN case for Mercedes-Benz article omissions.', variants: [{ file: '/bpmn/drn/case_008_Mercedes-Benz_article_omits_the_car_comp.bpmn' }] },
      { id: 'drn-homeopathy', label: 'Homeopathy - mention summary or description', description: 'DRN case for Homeopathy article description.', variants: [{ file: '/bpmn/drn/case_009_Homeopathy_-_to_mention_a_summary_or_the.bpmn' }] },
      { id: 'drn-chinaman', label: 'Chinaman term - whether to include information', description: 'DRN case for Chinaman term usage.', variants: [{ file: '/bpmn/drn/case_010_Chinaman_term_-_whether_to_include_infor.bpmn' }] },
      { id: 'drn-aggregate', label: 'Aggregate Workflow', description: 'Generalised BPMN workflow showing common process paths across all DRN cases.', variants: [{ file: '/bpmn/drn/drn_aggregate_workflow.bpmn' }] },
    ],
  },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function ViewToggle({ mode, onChange }) {
  const btn = (val, label) => (
    <button
      onClick={() => onChange(val)}
      style={{
        padding: '3px 10px',
        fontSize: 11,
        fontWeight: mode === val ? 600 : 400,
        background: mode === val ? 'var(--accent)' : 'transparent',
        color: mode === val ? '#fff' : 'var(--text-muted)',
        border: 'none',
        cursor: 'pointer',
        lineHeight: 1.6,
        transition: 'background 0.12s',
      }}
    >
      {label}
    </button>
  )
  return (
    <div style={{ display: 'flex', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden', flexShrink: 0 }}>
      {btn('bpmn', 'BPMN XML')}
      {btn('png', 'PNG')}
    </div>
  )
}

function KpiPill({ label, value }) {
  return (
    <div style={{
      flex: '1 1 0', minWidth: 0, display: 'flex', flexDirection: 'column',
      alignItems: 'center', background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 8, padding: '5px 8px',
    }}>
      <span style={{
        fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textAlign: 'center',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%',
        textTransform: 'uppercase', letterSpacing: '0.03em',
      }}>{label}</span>
      <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--accent)', whiteSpace: 'nowrap' }}>{value}</span>
    </div>
  )
}

function CaseKpis({ stats, sectionId }) {
  if (!stats) return null
  const pills = []
  if (stats.userLinks     != null) pills.push({ label: 'Unique User Refs',      value: stats.userLinks })
  if (stats.userTalkLinks != null) pills.push({ label: 'Unique User Talk Refs', value: stats.userTalkLinks })
  if (stats.wikiRefs      != null) pills.push({ label: 'Wikipedia (WP:) Refs',  value: stats.wikiRefs })
  if (sectionId === 'arbitration' && stats.wikiTalkRefs != null)
    pills.push({ label: 'Wikipedia Talk Refs', value: stats.wikiTalkRefs })
  if (sectionId === 'rfc' && stats.status)
    pills.push({ label: 'Status', value: stats.status })
  if (pills.length === 0) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'nowrap', gap: 6, margin: '10px 0 4px' }}>
      {pills.map(p => <KpiPill key={p.label} label={p.label} value={p.value} />)}
    </div>
  )
}

function ViewerSuspense({ url }) {
  return (
    <Suspense fallback={<div style={{ color: 'var(--text-muted)', padding: 24 }}>Loading viewer…</div>}>
      <BpmnViewer key={url} url={url} />
    </Suspense>
  )
}

/** One variant block: sub-header (if labelled) + toggle + diagram */
function VariantBlock({ variant, viewMode, onToggle, onExpand }) {
  const showLabel = !!variant.variantLabel
  return (
    <div style={{ marginBottom: 20 }}>
      {showLabel && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '7px 12px',
          background: 'var(--surface2, var(--surface))',
          border: '1px solid var(--border)',
          borderRadius: '6px 6px 0 0',
          borderBottom: 'none',
        }}>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{variant.variantLabel}</span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {variant.url && (
              <a href={variant.url} target="_blank" rel="noreferrer"
                style={{ fontSize: 11, color: 'var(--accent)', textDecoration: 'none', whiteSpace: 'nowrap' }}>
                Wikipedia ↗
              </a>
            )}
            <ViewToggle mode={viewMode} onChange={onToggle} />
            <button
              onClick={() => onExpand(variant)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', padding: '2px 4px' }}
              title="Expand"
            >
              <Maximize2 size={13} />
            </button>
          </div>
        </div>
      )}
      <div style={{
        height: 420,
        border: '1px solid var(--border)',
        borderRadius: showLabel ? '0 0 6px 6px' : 6,
        overflow: 'hidden',
        background: viewMode === 'png' ? 'var(--surface)' : '#fff',
      }}>
        {viewMode === 'bpmn' ? (
          <ViewerSuspense url={variant.file} />
        ) : (
          <div style={{ height: '100%', overflow: 'auto', display: 'flex', justifyContent: 'center', padding: 12 }}>
            <img
              src={pngFrom(variant.file)}
              alt={variant.variantLabel || 'BPMN diagram'}
              style={{ maxWidth: '100%', height: 'auto', borderRadius: 4 }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function BpmnScreen() {
  const [activeSection, setActiveSection] = useState(SECTIONS[0])
  const [selected, setSelected]           = useState(SECTIONS[0].cases[0] ?? null)
  const [viewModes, setViewModes]         = useState({})       // { [filePath]: 'bpmn' | 'png' }
  const [expandedVariant, setExpandedVariant] = useState(null) // variant object | null
  const [caseStats, setCaseStats]         = useState({})

  useEffect(() => {
    fetch('/data/dashboard_data.json')
      .then(r => r.ok ? r.json() : null)
      .then(json => { if (json?.caseStats) setCaseStats(json.caseStats) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!expandedVariant) return
    const handler = (e) => { if (e.key === 'Escape') setExpandedVariant(null) }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [expandedVariant])

  const getMode = (filePath) => viewModes[filePath] ?? 'bpmn'
  const setMode = (filePath, mode) => setViewModes(prev => ({ ...prev, [filePath]: mode }))

  const handleSection = (section) => {
    setActiveSection(section)
    setSelected(section.cases[0] ?? null)
  }

  const isMulti       = (selected?.variants?.length ?? 0) > 1
  const singleVariant = !isMulti ? selected?.variants?.[0] : null

  // KPI stats use the first (rules-based) variant's stem
  const primaryStem = selected?.variants?.[0] ? stemFromFile(selected.variants[0].file) : null
  const stats = primaryStem ? caseStats[primaryStem] : null

  // Resolve Wikipedia URL: prefer stats-derived URL, fall back to hardcoded variant URL
  const caseUrl = (() => {
    if (activeSection.id === 'drn') return stats?.sourceUrl || singleVariant?.url || null
    return stats?.url || singleVariant?.url || null
  })()

  return (
    <div className="bpmn-screen">
      {/* ── Section header ── */}
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

      {/* ── Body ── */}
      <div className="bpmn-body">
        {/* Left panel */}
        <aside className="bpmn-panel">
          <div className="bpmn-panel__title">Cases</div>
          {activeSection.cases.length === 0 ? (
            <div className="bpmn-panel__empty">No BPMN diagrams yet for {activeSection.label}.</div>
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

        {/* Viewer */}
        <div className="bpmn-viewer">
          {selected ? (
            <>
              {/* Case header */}
              <div className="bpmn-viewer__header">
                <div style={{ minWidth: 0, flex: 1 }}>
                  <h2>{selected.label}</h2>
                  <div className="bpmn-viewer__desc">{selected.description}</div>
                  {caseUrl && (
                    <a className="bpmn-viewer__link" href={caseUrl} target="_blank" rel="noreferrer">
                      View on Wikipedia ↗
                    </a>
                  )}
                  <CaseKpis stats={stats} sectionId={activeSection.id} />
                </div>

                {/* Single-variant controls (multi-variant has per-block controls) */}
                {!isMulti && singleVariant && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                    <ViewToggle
                      mode={getMode(singleVariant.file)}
                      onChange={(m) => setMode(singleVariant.file, m)}
                    />
                    <button
                      className="bpmn-expand-btn"
                      onClick={() => setExpandedVariant(singleVariant)}
                      title="Expand diagram"
                    >
                      <Maximize2 size={15} />
                    </button>
                  </div>
                )}
              </div>

              {/* Diagram area */}
              {isMulti ? (
                // Multi-variant: stacked, scrollable
                <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
                  {selected.variants.map(v => (
                    <VariantBlock
                      key={v.file}
                      variant={v}
                      viewMode={getMode(v.file)}
                      onToggle={(m) => setMode(v.file, m)}
                      onExpand={(variant) => setExpandedVariant(variant)}
                    />
                  ))}
                </div>
              ) : (
                // Single-variant
                <div className={`bpmn-viewer__body${getMode(singleVariant?.file) === 'bpmn' ? ' bpmn-viewer__body--xml' : ''}`}>
                  {singleVariant && (
                    getMode(singleVariant.file) === 'bpmn' ? (
                      <ViewerSuspense url={singleVariant.file} />
                    ) : (
                      <div style={{ display: 'flex', justifyContent: 'center', padding: 16, width: '100%' }}>
                        <img
                          src={pngFrom(singleVariant.file)}
                          alt={selected.label}
                          style={{ maxWidth: '100%', height: 'auto', borderRadius: 4, border: '1px solid var(--border)' }}
                        />
                      </div>
                    )
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="bpmn-viewer__empty">
              <span>No diagrams in this section yet.</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Fullscreen overlay ── */}
      {expandedVariant && (
        <div className="bpmn-overlay" onClick={() => setExpandedVariant(null)}>
          <div className="bpmn-overlay__panel" onClick={e => e.stopPropagation()}>
            <div className="bpmn-overlay__header">
              <span className="bpmn-overlay__title">
                {expandedVariant.variantLabel || selected?.label}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ViewToggle
                  mode={getMode(expandedVariant.file)}
                  onChange={(m) => setMode(expandedVariant.file, m)}
                />
                <button className="bpmn-overlay__close" onClick={() => setExpandedVariant(null)} title="Close (Esc)">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="bpmn-overlay__body" style={getMode(expandedVariant.file) === 'png' ? { background: 'var(--surface)', overflow: 'auto' } : undefined}>
              {getMode(expandedVariant.file) === 'bpmn' ? (
                <ViewerSuspense url={expandedVariant.file} />
              ) : (
                <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}>
                  <img
                    src={pngFrom(expandedVariant.file)}
                    alt={expandedVariant.variantLabel || ''}
                    style={{ maxWidth: '100%', height: 'auto' }}
                  />
                </div>
              )}
            </div>
            <div className="bpmn-overlay__hint">Press Esc or click outside to close</div>
          </div>
        </div>
      )}
    </div>
  )
}
