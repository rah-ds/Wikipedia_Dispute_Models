const VISUALS = [
  {
    id: 'case-browser',
    title: 'Editor Dispute Case Browser',
    description:
      'Interactive per-case editor dispute explorer: select a case to see editor timelines, edit wars, and DRN activity.',
    src: '/d3/case_browser.html',
    tall: true,
  },
  {
    id: 'arbitration-timeline',
    title: 'Arbitration Cases Timeline',
    description:
      'Timeline of arbitration case activity using D3, with each case shown as a span from earliest to latest revision.',
    src: '/d3/arbitration_timeline.html',
  },
  {
    id: 'recurring-editor-disputes',
    title: 'Recurring Editor Disputes',
    description:
      'Grouped ArbCom timelines for editors who appeared in multiple arbitration cases.',
    src: '/d3/recurring_editor_disputes.html',
  },
  {
    id: 'recurring-arbitration-timeline',
    title: 'Recurring Arbitration Disputes',
    description:
      'Grouped topic timelines showing disputes that resurfaced across multiple arbitration cases.',
    src: '/d3/recurring_arbitration_timeline.html',
  },
]

export default function D3Screen() {
  return (
    <div className="d3-screen">
      <div className="screen-header">
        <h1>D3 Visuals</h1>
        <p>Interactive D3 dispute visualizations embedded directly in the dashboard.</p>
      </div>

      <div className="d3-grid">
        {VISUALS.map((visual) => (
          <section key={visual.id} className={`d3-card${visual.tall ? ' d3-card--tall' : ''}`}>
            <div className="d3-card__header">
              <div>
                <h2>{visual.title}</h2>
                <p>{visual.description}</p>
              </div>
              <a
                className="d3-card__link"
                href={visual.src}
                target="_blank"
                rel="noreferrer"
              >
                Open full page ↗
              </a>
            </div>

            <div className="d3-frame-wrap">
              <iframe
                className="d3-frame"
                src={visual.src}
                title={visual.title}
                loading="lazy"
              />
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
