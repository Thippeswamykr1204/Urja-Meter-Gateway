import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { StaleBanner } from '../../components/StaleBanner'

const rules: Record<string, { severity: string; explanation: string }> = {
  missing: { severity: 'warning', explanation: 'The source omitted a value. It remains null and is excluded from sums.' },
  invalid: { severity: 'high', explanation: 'The value or timestamp could not be parsed safely.' },
  unknown_unit: { severity: 'warning', explanation: 'No verified unit was available, so the reading is not summed with known units.' },
  mixed_unit: { severity: 'high', explanation: 'A rollup contains more than one unit and therefore has no total.' },
  conflict: { severity: 'warning', explanation: 'A later value replaced an earlier value at the same meter timestamp; both are retained in conflict storage.' },
  counter_reset: { severity: 'warning', explanation: 'A cumulative counter decreased. The incompatible delta is omitted.' },
  orphan: { severity: 'warning', explanation: 'A hierarchy parent or meter placement was not observed.' },
  cycle: { severity: 'high', explanation: 'A parent relationship would create a cycle; the record is retained as a root.' },
}

export function QualityPage() {
  const quality = useQuery({ queryKey: ['quality'], queryFn: api.quality })
  const signals = useQuery({ queryKey: ['signals'], queryFn: api.signals })
  const data = quality.data?.data
  return <div className="page-grid"><section className="page-intro compact"><div><span className="eyebrow accent-text">TRUST / EXPLANATIONS</span><h1>Data quality</h1><p>Quality flags make uncertainty legible. They do not silently repair the source.</p></div></section><StaleBanner provenance={quality.data?.provenance} />{quality.isLoading ? <LoadingState lines={5} /> : quality.isError ? <ErrorState title="Quality report unavailable" error={quality.error} retry={() => quality.refetch()} /> : data ? <><div className="quality-overview"><div className="quality-score"><span className="eyebrow">RECORDS CHECKED</span><strong>{data.total_records}</strong><small>{data.issue_count ? `${data.issue_count} issue signals` : 'No issues recorded'}</small></div><div className="quality-score"><span className="eyebrow">SOURCE POSTURE</span><strong>Explicit</strong><small>Provenance attached to every response</small></div><div className="quality-score"><span className="eyebrow">MISSING VALUES</span><strong>Not zero</strong><small>Missing readings remain missing</small></div></div><div className="dashboard-columns"><Panel eyebrow="FLAG COUNTS" title="What needs attention"><div className="flag-list">{Object.entries(data.by_flag).length ? Object.entries(data.by_flag).map(([flag, count]) => { const rule = rules[flag] ?? { severity: 'info', explanation: 'No additional interpretation has been configured for this flag.' }; return <div className="flag-row" key={flag}><span className="flag-icon"><AlertTriangle size={15} /></span><span><strong>{flag}</strong><small>{rule.severity} · {rule.explanation}</small></span><strong>{count}</strong><small className="flag-example">{data.examples[flag]?.[0] ?? 'No example note'}</small></div> }) : <EmptyState title="No quality flags" detail="The indexed records are clean under the current rules." />}</div></Panel><Panel eyebrow="SIGNALS" title="Observed patterns"><div className="quality-notes">{signals.isError ? <ErrorState title="Signals unavailable" error={signals.error} retry={() => signals.refetch()} /> : signals.data?.data.length ? signals.data.data.map((signal) => <div key={`${signal.meter_id}-${signal.kind}-${signal.timestamp}`}><AlertTriangle size={17} /><p><Link className="inline-link" to={`/meters/${signal.meter_id}`}>{signal.meter_id}</Link> · {signal.kind}: {signal.detail}. Observed {signal.observed_value ?? 'unknown'}, baseline {signal.baseline ?? 'not applicable'}; this is a signal, not a verdict.</p></div>) : <div><CheckCircle2 size={17} /><p>No observed anomaly signals with sufficient history.</p></div>}</div></Panel></div><Panel eyebrow="INTERPRETATION" title="Read this report"><div className="quality-notes"><div><CheckCircle2 size={17} /><p>Missing values, invalid values, and unknown units remain distinguishable. Rollups sum only compatible, valid values.</p></div><div><Info size={17} /><p>Signals are conservative and require sufficient history. They point to a meter and rule so an operator can inspect the raw series.</p></div></div></Panel></> : <EmptyState title="No quality report" detail="Run an indexed sync before reviewing quality." />}</div>
}
