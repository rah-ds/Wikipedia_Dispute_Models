import { useEffect, useRef } from 'react'
import BpmnViewer from 'bpmn-js/lib/Viewer'
import 'bpmn-js/dist/assets/diagram-js.css'
import 'bpmn-js/dist/assets/bpmn-js.css'
import 'bpmn-js/dist/assets/bpmn-font/css/bpmn.css'

function fitToContainer(viewer) {
  viewer.get('canvas').zoom('fit-viewport', 'auto')
}

export default function BpmnViewerComponent({ url }) {
  const containerRef = useRef(null)
  const viewerRef    = useRef(null)

  useEffect(() => {
    viewerRef.current = new BpmnViewer({ container: containerRef.current })
    return () => viewerRef.current?.destroy()
  }, [])

  useEffect(() => {
    if (!url || !viewerRef.current) return
    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.text()
      })
      .then(xml => viewerRef.current.importXML(xml))
      .then(() => requestAnimationFrame(() => fitToContainer(viewerRef.current)))
      .catch(err => console.error('BpmnViewer: failed to load', url, err))
  }, [url])

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(() => {
      if (viewerRef.current) requestAnimationFrame(() => fitToContainer(viewerRef.current))
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', minHeight: 480, position: 'relative' }}
    />
  )
}
