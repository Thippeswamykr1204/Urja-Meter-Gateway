import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ArrowLeft, CircleAlert, MapPin } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { api } from '../../lib/api'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'
import { StatusPill } from '../../components/StatusPill'

export function MeterDetail() {
  const { meterId = '' } = useParams()
  const [granularity, setGranularity] = useState<'hour' | 'day' | 'month'>('day')
  const [range, setRange] = useState('14')
  const meter = useQuery({ queryKey: ['meter', meterId], queryFn: () => api.meter(meterId) })
  const start = new Date(Date.now() - Number(range) * 86400000).toISOString().slice(0, 10)
  const consumption = useQuery({ queryKey: ['consumption', meterId, granularity, range], queryFn: () => api.consumption(meterId, `?granularity=${granularity}&start=${start}`), enabled: Boolean(meterId) })
  if (meter.isLoading) return <LoadingState lines={5} />
  if (!meter.data) return <div className="error-state"><CircleAlert size={22} /><h2>Meter unavailable</h2><p>The local index did not return this signal.</p></div>
  const item = meter.data.data
  const points = (consumption.data?.data.points ?? []).filter((point) => point.timestamp)
  const unit = consumption.data?.data.summary.unit ?? points.find((point) => point.unit)?.unit ?? 'unit unavailable'
  const chartOption = { grid: { left: 8, right: 8, top: 20, bottom: 24, containLabel: true }, xAxis: { type: 'category', data: points.map((point) => new Date(point.timestamp!).toLocaleDateString([], { month: 'short', day: 'numeric' })), axisLabel: { color: '#7e897d' }, axisLine: { lineStyle: { color: '#2b3328' } } }, yAxis: { type: 'value', axisLabel: { color: '#7e897d' }, splitLine: { lineStyle: { color: '#20281e' } } }, tooltip: { trigger: 'axis' }, series: [{ data: points.map((point) => point.value), type: 'line', smooth: true, symbol: 'circle', symbolSize: 7, lineStyle: { color: '#d9f26d', width: 3 }, itemStyle: { color: '#d9f26d', borderColor: '#11140f', borderWidth: 2 }, areaStyle: { color: 'rgba(217,242,109,.12)' } }] }
  return <div className="page-grid"><Link to="/meters" className="back-link"><ArrowLeft size={15} /> Back to explorer</Link><section className="detail-hero"><div><span className="eyebrow accent-text">METER / {item.id}</span><h1>{item.name ?? item.id}</h1><div className="detail-meta"><StatusPill status={item.status} /><QualityBadge quality={item.quality} /><span className="mono-cell">{item.serial_number ?? 'serial unavailable'}</span></div></div><div className="coordinate"><MapPin size={17} /><span>{item.latitude?.toFixed(4) ?? '—'}, {item.longitude?.toFixed(4) ?? '—'}</span></div></section><div className="detail-columns"><Panel eyebrow={`CONSUMPTION / ${range} DAYS`} title="Energy signal" action={<div className="chart-controls"><select aria-label="Consumption range" value={range} onChange={(event) => setRange(event.target.value)}><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select><select aria-label="Consumption granularity" value={granularity} onChange={(event) => setGranularity(event.target.value as typeof granularity)}><option value="hour">Hour</option><option value="day">Day</option><option value="month">Month</option></select></div>}><div className="chart-wrap">{consumption.isLoading ? <LoadingState lines={4} /> : consumption.isError ? <div className="error-state"><h2>Consumption unavailable</h2><p>{(consumption.error as Error).message}</p></div> : <ReactECharts option={chartOption} style={{ height: 300, width: '100%' }} opts={{ renderer: 'svg' }} />}</div><div className="chart-summary"><div><span>Total</span><strong>{consumption.data?.data.summary.total?.toFixed(1) ?? '—'} {unit}</strong></div><div><span>Average</span><strong>{consumption.data?.data.summary.average?.toFixed(1) ?? '—'} {unit}</strong></div><div><span>Points</span><strong>{points.length}</strong></div></div></Panel><Panel eyebrow="SIGNAL CONTEXT" title="What to know"><div className="context-list"><div><span>Last seen</span><strong>{item.last_seen_at ? new Date(item.last_seen_at).toLocaleString() : 'Unavailable'}</strong></div><div><span>Network node</span><strong>{item.network_node_id ?? 'Unverified'}</strong></div><div><span>Source</span><strong>{consumption.data?.provenance.source ?? item.provenance.source}</strong></div><div><span>Freshness</span><strong>{consumption.data?.provenance.stale ? 'Stale' : 'Current'}</strong></div></div><div className="signal-note"><CircleAlert size={16} /><p>Signals are descriptive. A spike or gap is not a maintenance verdict.</p></div></Panel></div></div>
}
