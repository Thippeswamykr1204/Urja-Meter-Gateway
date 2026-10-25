import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ArrowUpRight, Filter, RefreshCw, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'
import { StatusPill } from '../../components/StatusPill'

export function MeterExplorer() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState('id')
  const [order, setOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const pageSize = 25
  const query = `${search ? `&search=${encodeURIComponent(search)}` : ''}${status ? `&status=${encodeURIComponent(status)}` : ''}&sort=${sort}&order=${order}`
  const meters = useQuery({ queryKey: ['meters', page, query], queryFn: () => api.meterPage(page, pageSize, query) })
  const data = meters.data?.data ?? []
  const meta = meters.data?.meta as { page?: number; total?: number; has_next?: boolean } | undefined

  const toggleSort = (next: string) => {
    if (sort === next) setOrder(order === 'asc' ? 'desc' : 'asc')
    else { setSort(next); setOrder('asc') }
    setPage(1)
  }

  return <div className="page-grid"><section className="page-intro compact"><div><span className="eyebrow accent-text">CATALOG / {meta?.total ?? '—'} INDEXED</span><h1>Meter explorer</h1><p>Search the indexed fleet and open a signal without touching the legacy portal.</p></div><div className="intro-note"><span className="live-dot" /> {meters.data?.provenance.stale ? 'stale index' : 'current index'}</div></section><Panel title="Indexed fleet" eyebrow="SERVER-SIDE QUERY"><div className="toolbar"><label className="search-field"><Search size={16} /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Search id, serial or name" /></label><label className="select-field"><Filter size={15} /><select value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}><option value="">All statuses</option><option value="active">Active</option><option value="warning">Warning</option><option value="offline">Offline</option></select></label><button className="icon-button" aria-label="Retry meter query" onClick={() => meters.refetch()}><RefreshCw size={16} /></button></div>{meters.isLoading ? <LoadingState lines={6} /> : meters.isError ? <div className="error-state"><h2>Meter query failed</h2><p>{(meters.error as Error).message}</p><button className="button button-ghost" onClick={() => meters.refetch()}>Try again</button></div> : data.length === 0 ? <EmptyState title="No meters match" detail="Try a broader search or remove the status filter." /> : <><div className="table-wrap"><table><thead><tr><th><button className="table-sort" onClick={() => toggleSort('name')}>Meter {sort === 'name' ? (order === 'asc' ? '↑' : '↓') : ''}</button></th><th>Status</th><th><button className="table-sort" onClick={() => toggleSort('last_seen_at')}>Last seen {sort === 'last_seen_at' ? (order === 'asc' ? '↑' : '↓') : ''}</button></th><th>Quality</th><th /></tr></thead><tbody>{data.map((meter) => <tr key={meter.id}><td><div className="table-primary"><span className="meter-avatar">{meter.id.slice(-2)}</span><div><Link to={`/meters/${meter.id}`} className="table-link">{meter.name ?? meter.id}</Link><small>{meter.serial_number ?? 'serial unavailable'} · {meter.id}</small></div></div></td><td><StatusPill status={meter.status} /></td><td className="mono-cell">{meter.last_seen_at ? new Date(meter.last_seen_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'unavailable'}</td><td><QualityBadge quality={meter.quality} /></td><td><Link to={`/meters/${meter.id}`} className="icon-link" aria-label={`Open ${meter.id}`}><ArrowUpRight size={16} /></Link></td></tr>)}</tbody></table></div><div className="pagination"><span>{meta?.total ?? 0} meters · page {page}</span><div><button className="icon-button" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}><ArrowLeft size={16} /></button><button className="icon-button" aria-label="Next page" disabled={!meta?.has_next} onClick={() => setPage(page + 1)}><ArrowRight size={16} /></button></div></div></>}</Panel></div>
}
