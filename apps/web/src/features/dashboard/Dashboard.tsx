import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { MetricCard } from '../../components/MetricCard'
import { Panel } from '../../components/Panel'
import { StatusPill } from '../../components/StatusPill'
import { LoadingState } from '../../components/LoadingState'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { StaleBanner } from '../../components/StaleBanner'
import { WidgetBoundary } from '../../components/ErrorBoundary'

export function Dashboard() {
  const overview = useQuery({ queryKey: ['overview'], queryFn: api.overview, refetchInterval: 30_000 })
  const meters = useQuery({ queryKey: ['meters', 'overview'], queryFn: () => api.meters() })
  const ready = useQuery({ queryKey: ['ready'], queryFn: api.ready, refetchInterval: 30_000 })
  const quality = useQuery({ queryKey: ['quality'], queryFn: api.quality })
  const sync = useQuery({ queryKey: ['sync'], queryFn: api.sync, refetchInterval: 10_000 })
  const stats = overview.data?.data
  const data = meters.data?.data ?? []
  const active = stats?.status_counts.active ?? 0
  const signalCount = stats?.signal_count ?? 0
  const trend = stats?.load_trend ?? []
  const maxLoad = Math.max(...trend.map((point) => point.total), 1)
  const sparkline = trend.map((point, index) => `${trend.length <= 1 ? 0 : (index / (trend.length - 1)) * 100},${44 - (point.total / maxLoad) * 36}`).join(' ')

  const refreshing = async () => {
    await api.refresh()
    await Promise.all([overview.refetch(), meters.refetch(), quality.refetch(), sync.refetch()])
  }

  if (overview.isError && !stats) {
    return <ErrorState title="Overview unavailable" error={overview.error} retry={() => overview.refetch()} />
  }

  return <div className="page-grid">
    <section className="page-intro"><div><span className="eyebrow accent-text">FIELD SIGNAL / {signalCount} SIGNALS</span><h1>See the grid<br /><em>without the noise.</em></h1><p>A quiet operating surface for the meters that keep the network moving.</p></div><button className="button button-ghost" onClick={refreshing} disabled={sync.data?.data.status === 'running'}><RefreshCw size={15} /> {sync.data?.data.status === 'running' ? 'Refreshing…' : 'Refresh index'}</button></section>
    <div className="metric-grid"><MetricCard label="Indexed meters" value={overview.isLoading ? '—' : String(stats?.meter_count ?? 0).padStart(2, '0')} detail="full local catalog" accent /><MetricCard label="Reporting normally" value={overview.isLoading ? '—' : `${Math.round((active / Math.max(stats?.meter_count ?? 1, 1)) * 100)}%`} detail={`${active} active signals`} /><MetricCard label="Needs attention" value={overview.isLoading ? '—' : String(signalCount).padStart(2, '0')} detail="explainable signal markers" /><MetricCard label="Source posture" value={ready.data?.portal?.mode === 'demo' ? 'DEMO' : 'LIVE'} detail={ready.data?.status === 'ready' ? 'ready to serve' : 'attention required'} /> </div>
     <StaleBanner provenance={overview.data?.provenance} /><div className="dashboard-columns"><WidgetBoundary title="Meter status unavailable"><Panel eyebrow="CURRENT SIGNAL" title="Status breakdown" action={<Link className="inline-link" to="/meters">All meters <ArrowUpRight size={14} /></Link>}><div className="status-breakdown">{meters.isLoading ? <LoadingState lines={4} /> : meters.isError ? <ErrorState title="Meter status unavailable" error={meters.error} retry={() => meters.refetch()} /> : data.length ? data.map((meter) => <Link to={`/meters/${meter.id}`} className="status-row" key={meter.id}><div><span className="meter-avatar">{meter.id.slice(-2)}</span><div><strong>{meter.name ?? meter.id}</strong><small>{meter.serial_number ?? 'serial unavailable'}</small></div></div><StatusPill status={meter.status} /></Link>) : <EmptyState title="No meter signals" detail="Refresh the index or configure the portal evidence." />}</div></Panel></WidgetBoundary><WidgetBoundary title="Quality unavailable"><Panel eyebrow="DATA HEALTH" title="Freshness & quality"><div className="health-summary"><div className="health-ring"><span>{quality.data?.data.issue_count ?? 0}</span><small>{quality.data?.data.issue_count ? 'attention' : 'issues'}</small></div><div className="health-copy"><strong>{quality.data?.data.issue_count ? 'Attention suggested' : 'Clean enough to work'}</strong><p>{quality.data?.data.total_records ?? 0} indexed records checked against the local quality rules.</p><Link className="inline-link" to="/quality">Open quality report <ArrowUpRight size={14} /></Link></div></div><div className={`freshness-bar ${overview.data?.provenance.stale ? 'freshness-stale' : ''}`}><span /><div><strong>{overview.data?.provenance.stale ? 'Index is stale' : 'Index is current'}</strong><small>{overview.data?.provenance.age_seconds?.toFixed(0) ?? '—'} seconds old · sync status: {sync.data?.data.status ?? 'unknown'}</small></div></div></Panel></WidgetBoundary></div>
    <Panel eyebrow="INDEXED LOAD" title="Total load trend"><div className="trend-panel"><div className="trend-value"><strong>{trend.length ? `${trend[trend.length - 1].total.toFixed(1)} kWh` : '—'}</strong><small>{trend.length ? `${trend.length} observed days` : 'No reading trend available'}</small></div>{trend.length > 1 ? <svg className="sparkline" viewBox="0 0 100 48" preserveAspectRatio="none" role="img" aria-label="Total load trend"><polyline points={sparkline} fill="none" stroke="currentColor" strokeWidth="2.5" vectorEffect="non-scaling-stroke" /></svg> : <EmptyState title="No trend yet" detail="Index readings to see total load over time." />}</div></Panel>
    {overview.isLoading && <LoadingState />}
  </div>
}
