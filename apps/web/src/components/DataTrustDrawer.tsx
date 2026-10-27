import { ShieldCheck, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Provenance, QualitySummary, Signal } from '../lib/types'
import { qualityFlagExplanations } from '../lib/quality'

const NOT_REPORTED = 'Not reported by the portal'

function display(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === '') return NOT_REPORTED
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

function focusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  ))
}

export function DataTrustDrawer({
  provenance,
  quality,
  signals = [],
  label = 'Data trust',
}: {
  provenance?: Provenance | null
  quality?: QualitySummary | null
  signals?: Signal[]
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const drawerRef = useRef<HTMLElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const trigger = triggerRef.current
    closeRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setOpen(false)
        return
      }
      if (event.key !== 'Tab' || !drawerRef.current) return
      const elements = focusableElements(drawerRef.current)
      if (!elements.length) return
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previous?.focus()
      trigger?.focus()
    }
  }, [open])

  const flags = quality?.flags ?? []

  return <>
    <button ref={triggerRef} className="trust-trigger" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open} aria-label={label}>
      <ShieldCheck size={15} /> {label}
    </button>
    {open && <div className="trust-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false) }}>
      <aside ref={drawerRef} className="trust-drawer" role="dialog" aria-modal="true" aria-labelledby="trust-title">
        <header className="trust-header">
          <div><span className="eyebrow">PROVENANCE / QUALITY</span><h2 id="trust-title">Data trust</h2></div>
          <button ref={closeRef} className="icon-button" onClick={() => setOpen(false)} aria-label="Close data trust drawer"><X size={18} /></button>
        </header>
        <dl className="trust-list">
          <div><dt>Source</dt><dd>{display(provenance?.source)}</dd></div>
          <div><dt>Fetched at</dt><dd>{display(provenance?.fetched_at)}</dd></div>
          <div><dt>Indexed at</dt><dd>{display(provenance?.indexed_at)}</dd></div>
          <div><dt>Portal timestamp</dt><dd>{display(provenance?.portal_timestamp)}</dd></div>
          <div><dt>Age</dt><dd>{provenance?.age_seconds == null ? NOT_REPORTED : `${Math.round(provenance.age_seconds)} seconds`}</dd></div>
          <div><dt>Stale</dt><dd>{display(provenance?.stale)}</dd></div>
        </dl>
        <section className="trust-section"><h3>Quality flags</h3>{flags.length ? <ul className="trust-flags">{flags.map((flag) => <li key={flag}><strong>{flag}</strong><span>{qualityFlagExplanations[flag]}</span></li>)}</ul> : <p className="trust-empty">No quality flags were recorded.</p>}</section>
        {signals.length > 0 && <section className="trust-section"><h3>Anomaly signals</h3><ul className="trust-flags">{signals.map((signal) => <li key={`${signal.kind}-${signal.timestamp ?? 'none'}`}><strong>{signal.kind}</strong><span>{signal.detail}. Observed: {display(signal.observed_value)} · baseline: {display(signal.baseline)} · rule: {display(signal.rule)} · sufficient history: {display(signal.sufficient_history)}.</span></li>)}</ul></section>}
      </aside>
    </div>}
  </>
}
