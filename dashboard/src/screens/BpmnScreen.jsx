import { useState } from 'react'

const DIAGRAMS = [
  {
    id: 'aggregate',
    label: 'BPMN Aggregate',
    file: '/bpmn/BPMN_Aggregate.png',
    description:
      'High-level aggregate process model showing the overall arbitration lifecycle — ' +
      'from case filing through deliberation to final decision and enforcement.',
  },
  {
    id: 'power-electronics',
    label: 'Power Electronics Case',
    file: '/bpmn/BPMN_Power_Electronics.png',
    description:
      'BPMN model for the Power Electronics arbitration case, illustrating content ' +
      'dispute escalation, evidence gathering, and sanction application.',
  },
  {
    id: 'rfc',
    label: 'RFC Process',
    file: '/bpmn/RFC.png',
    description:
      'Request for Comment (RFC) dispute resolution flow, detailing community ' +
      'participation steps before escalation to formal arbitration.',
  },
  {
    id: 'rfc-sysop',
    label: 'RFC Sysop Abuse',
    file: '/bpmn/RFC_SysopAbuse.png',
    description:
      'Specialised RFC track for administrator / sysop conduct complaints, ' +
      'showing the handling path for alleged administrative misconduct.',
  },
]

export default function BpmnScreen() {
  const [selected, setSelected] = useState(DIAGRAMS[0])
  const [imgError, setImgError] = useState(false)

  const handleSelect = (diagram) => {
    setSelected(diagram)
    setImgError(false)
  }

  return (
    <div>
      <div className="screen-header">
        <h1>Process Diagrams</h1>
        <p>BPMN models derived from Wikipedia arbitration and dispute-resolution workflows.</p>
      </div>

      <div className="bpmn-layout">
        {/* Sidebar */}
        <aside className="bpmn-sidebar">
          <div className="bpmn-sidebar__title">Diagrams</div>
          {DIAGRAMS.map(d => (
            <button
              key={d.id}
              className={`bpmn-item${selected.id === d.id ? ' bpmn-item--active' : ''}`}
              onClick={() => handleSelect(d)}
            >
              {d.label}
            </button>
          ))}
        </aside>

        {/* Viewer */}
        <div className="bpmn-viewer">
          <div className="bpmn-viewer__header">
            <div>
              <h2>{selected.label}</h2>
              <div className="bpmn-viewer__desc">{selected.description}</div>
            </div>
            <span className="bpmn-badge">PNG</span>
          </div>

          <div className="bpmn-viewer__body">
            {imgError ? (
              <div style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                gap: 10, color: 'var(--text-muted)',
              }}>
                <span style={{ fontSize: 40 }}>🖼️</span>
                <span style={{ fontSize: 13 }}>Image could not be loaded.</span>
                <code style={{ fontSize: 11, background: 'var(--surface2)', padding: '4px 8px', borderRadius: 4 }}>
                  {selected.file}
                </code>
              </div>
            ) : (
              <img
                key={selected.id}
                src={selected.file}
                alt={selected.label}
                onError={() => setImgError(true)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
