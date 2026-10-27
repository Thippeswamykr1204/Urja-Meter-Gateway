import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ArrowUpRight, Download, Filter, RefreshCw, Search } from 'lucide-react'
import { motion } from 'framer-motion'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { DataTrustDrawer } from '../../components/DataTrustDrawer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'
import { StaleBanner } from '../../components/StaleBanner'
import { StatusPill } from '../../components/StatusPill'
import { api } from '../../lib/api'
import { useReducedMotionPreference } from '../../lib/useMotion'

function csvCell(value: string | number | null) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export function MeterExplorer() {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const reducedMotion = useReducedMotionPreference()
  const [searchInput, setSearchInput] = useState(params.get('search') ?? '')
  const [search, setSearch] = useState(params.get('search') ?? '')
  const [status, setStatus] = useState(params.get('status') ?? '')
  const [sort, setSort] = useState(params.get('sort') ?? 'id')
  const [order, setOrder] = useState<'asc' | 'desc'>(params.get('order') === 'desc' ? 'desc' : 'asc')
  const [page, setPage] = useState(Number(params.get('page') ?? '1') || 1)
  const pageSize = 25

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim())
      setPage(1)
    }, 250)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  useEffect(() => {
    const next = new URLSearchParams()
    if (search) next.set('search', search)
    if (status) next.set('status', status)
    if (sort !== 'id') next.set('sort', sort)
    if (order !== 'asc') next.set('order', order)
    if (page !== 1) next.set('page', String(page))
    setParams(next, { replace: true })
  }, [search, status, sort, order, page, setParams])

  const query = useMemo(() => `${search ? `&search=${encodeURIComponent(search)}` : ''}${status ? `&status=${encodeURIComponent(status)}` : ''}&sort=${sort}&order=${order}`, [search, status, sort, order])
  const meters = useQuery({ queryKey: ['meters', page, query], queryFn: () => api.meterPage(page, pageSize, query) })
  const data = meters.data?.data ?? []
  const meta = meters.data?.meta as { page?: number; total?: number; has_next?: boolean } | undefined

  const toggleSort = (next: string) => {
    if (sort === next) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(next); setOrder('asc') }
    setPage(1)
  }

  const downloadCsv = () => {
    const rows = [['id', 'serial_number', 'name', 'status', 'last_seen_at'], ...data.map((meter) => [meter.id, meter.serial_number, meter.name, meter.status, meter.last_seen_at])]
    const blob = new Blob([rows.map((row) => row.map(csvCell).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'meters-current-view.csv'
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return <div className="page-grid">
    <section className="page-intro compact"><div><span className="eyebrow accent-text">CATALOG / {meta?.total ?? '—'} INDEXED</span><h1>Meter explorer</h1><p>Search the indexed fleet and open a signal without touching the legacy portal.</p></div><div className="intro-actions"><div className="intro-note"><span className="live-dot" /> {meters.data?.provenance.stale ? 'stale index' : 'current index'}</div><button className="button button-ghost" onClick={downloadCsv} disabled={!data.length}><Download size={15} /> CSV view</button></div></section>
    <StaleBanner provenance={meters.data?.provenance} />
    <Panel title="Indexed fleet" eyebrow="SERVER-SIDE QUERY">
      <div className="toolbar"><label className="search-field"><Search size={16} /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search id, serial or name" aria-label="Search meters" /></label><label className="select-field"><Filter size={15} /><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }} aria-label="Filter by status"><option value="">All statuses</option><option value="active">Active</option><option value="warning">Warning</option><option value="offline">Offline</option></select></label><button className="icon-button" aria-label="Retry meter query" onClick={() => meters.refetch()}><RefreshCw size={16} /></button></div>
      {meters.isLoading ? <LoadingState lines={6} /> : meters.isError ? <ErrorState title="Meter query failed" error={meters.error} retry={() => meters.refetch()} /> : data.length === 0 ? <EmptyState title="No meters match" detail="Try a broader search or remove the status filter." /> : <>
        <div className="table-wrap"><table><thead><tr><th><button className="table-sort" onClick={() => toggleSort('name')}>Meter {sort === 'name' ? (order === 'asc' ? '↑' : '↓') : ''}</button></th><th>Status</th><th><button className="table-sort" onClick={() => toggleSort('last_seen_at')}>Last seen {sort === 'last_seen_at' ? (order === 'asc' ? '↑' : '↓') : ''}</button></th><th>Quality</th><th>Trust</th><th /></tr></thead><tbody>{data.map((meter) => <tr key={meter.id} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); navigate(`/meters/${meter.id}`, { state: { from: location.search } }) } }}><td><motion.div layoutId={reducedMotion ? undefined : `meter-${meter.id}`} className="table-primary"><span className="meter-avatar">{meter.id.slice(-2)}</span><div><Link to={`/meters/${meter.id}`} state={{ from: location.search }} className="table-link">{meter.name ?? meter.id}</Link><small>{meter.id} · {meter.serial_number ?? 'serial unavailable'}</small></div></motion.div></td><td><StatusPill status={meter.status} /></td><td className="mono-cell">{meter.last_seen_at ? new Date(meter.last_seen_at).toLocaleString() : 'not observed'}</td><td><QualityBadge quality={meter.quality} /></td><td><DataTrustDrawer provenance={meter.provenance} quality={meter.quality} label={`Trust for ${meter.name ?? meter.id}`} /></td><td><Link to={`/meters/${meter.id}`} state={{ from: location.search }} className="icon-link" aria-label={`Open ${meter.name ?? meter.id}`}><ArrowUpRight size={16} /></Link></td></tr>)}</tbody></table></div>
        <div className="pagination"><span>Page {page} · {meta?.total ?? data.length} total</span><div><button className="icon-button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(Math.max(1, page - 1))}><ArrowLeft size={16} /></button><button className="icon-button" aria-label="Next page" disabled={!meta?.has_next} onClick={() => setPage(page + 1)}><ArrowRight size={16} /></button></div></div>
      </>}
    </Panel>
  </div>
}
