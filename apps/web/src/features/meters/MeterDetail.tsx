import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { ArrowLeft, CircleAlert, MapPin } from 'lucide-react'
import { motion } from 'framer-motion'
import { Link, useLocation, useParams } from 'react-router-dom'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, MarkPointComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import { DataTrustDrawer } from '../../components/DataTrustDrawer'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'
import { StaleBanner } from '../../components/StaleBanner'
import { StatusPill } from '../../components/StatusPill'
import { api } from '../../lib/api'
import { useThemeColors } from '../../lib/theme'
import { useReducedMotionPreference } from '../../lib/useMotion'

echarts.use([LineChart, DataZoomComponent, GridComponent, MarkPointComponent, TooltipComponent, SVGRenderer])

export function MeterDetail() {
  const { meterId = '' } = useParams()
  const location = useLocation()
  const reducedMotion = useReducedMotionPreference()
  const colors = useThemeColors()
  const [granularity, setGranularity] = useState<'hour' | 'day' | 'month'>('day')
  const [range, setRange] = useState('14')
  const meter = useQuery({ queryKey: ['meter', meterId], queryFn: () => api.meter(meterId) })
  const start = new Date(Date.now() - Number(range) * 86400000).toISOString().slice(0, 10)
  const consumption = useQuery({ queryKey: ['consumption', meterId, granularity, range], queryFn: () => api.consumption(meterId, `?granularity=${granularity}&start=${start}`), enabled: Boolean(meterId) })
  const signals = useQuery({ queryKey: ['signals', meterId], queryFn: api.signals, enabled: Boolean(meterId) })
  const item = meter.data?.data
  const points = useMemo(() => consumption.data?.data.points ?? [], [consumption.data])
  const unit = consumption.data?.data.summary.unit ?? null
  const anomalies = useMemo(() => signals.data?.data.filter((signal) => signal.meter_id === meterId && signal.timestamp) ?? [], [meterId, signals.data])
  const option = useMemo<EChartsOption>(() => ({
    grid: { left: 8, right: 8, top: 20, bottom: 56, containLabel: true },
    xAxis: { type: 'category', data: points.map((point) => point.timestamp ? new Date(point.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' }) : 'unknown'), axisLabel: { color: colors['chart-axis'] }, axisLine: { lineStyle: { color: colors['chart-axis-line'] } } },
    yAxis: { type: 'value', name: unit ?? 'unknown unit', nameTextStyle: { color: colors['chart-axis'] }, axisLabel: { color: colors['chart-axis'] }, splitLine: { lineStyle: { color: colors['chart-grid'] } } },
    tooltip: { trigger: 'axis', backgroundColor: colors['chart-tooltip-background'], borderColor: colors['chart-tooltip-border'], textStyle: { color: colors['chart-tooltip-text'] }, shadowColor: colors['chart-shadow'] },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 10, borderColor: colors['chart-slider-border'], backgroundColor: colors['chart-slider-background'], fillerColor: colors['chart-slider-filler'], dataBackground: { lineStyle: { color: colors['chart-slider-data'] }, areaStyle: { color: colors['chart-slider-data'] } }, selectedDataBackground: { lineStyle: { color: colors['chart-slider-selected'] }, areaStyle: { color: colors['chart-slider-selected'] } }, handleStyle: { color: colors['chart-slider-handle'], borderColor: colors['chart-slider-handle-border'] }, emphasis: { handleLabel: { show: true }, handleStyle: { borderColor: colors['chart-slider-emphasis'] } }, textStyle: { color: colors['chart-axis'] } }],
    series: [{ data: points.map((point) => point.value), type: 'line', connectNulls: false, smooth: false, symbol: 'circle', symbolSize: 7, lineStyle: { color: colors.accent, width: 3 }, itemStyle: { color: colors.accent, borderColor: colors['on-accent'], borderWidth: 2 }, areaStyle: { color: colors['chart-area'] }, markPoint: { data: anomalies.map((signal) => ({ name: signal.kind, coord: [points.findIndex((point) => point.timestamp === signal.timestamp), signal.observed_value ?? 0], value: signal.kind })), itemStyle: { color: colors.warm } } }],
  }), [anomalies, colors, points, unit])

  if (meter.isLoading) return <LoadingState lines={5} />
  if (meter.isError) return <ErrorState title="Meter unavailable" error={meter.error} retry={() => meter.refetch()} />
  if (!item) return <div className="error-state"><CircleAlert size={22} /><h2>Meter unavailable</h2><p>The local index did not return this signal.</p></div>

  return <div className="page-grid">
    <Link to={(location.state as { from?: string } | null)?.from ? `/meters${(location.state as { from?: string }).from}` : '/meters'} className="back-link"><ArrowLeft size={15} /> Back to explorer</Link>
    <motion.section layoutId={reducedMotion ? undefined : `meter-${item.id}`} transition={reducedMotion ? { duration: 0 } : { duration: 0.2 }} className="detail-hero"><div><span className="eyebrow accent-text">METER / {item.id}</span><h1>{item.name ?? item.id}</h1><div className="detail-meta"><StatusPill status={item.status} /><QualityBadge quality={item.quality} /><span className="mono-cell">{item.serial_number ?? 'serial unavailable'}</span></div></div><div className="coordinate"><MapPin size={17} /><span>{item.latitude?.toFixed(4) ?? 'unknown latitude'}, {item.longitude?.toFixed(4) ?? 'unknown longitude'}</span></div></motion.section>
    <StaleBanner provenance={consumption.data?.provenance} />
    <div className="detail-trust"><DataTrustDrawer provenance={consumption.data?.provenance ?? item.provenance} quality={consumption.data?.data.quality ?? item.quality} signals={anomalies} /></div>
    <div className="detail-columns">
      <Panel eyebrow={`CONSUMPTION / ${range} DAYS`} title="Energy signal" action={<div className="chart-controls"><select aria-label="Consumption range" value={range} onChange={(event) => setRange(event.target.value)}><option value="7">7 days</option><option value="14">14 days</option><option value="30">30 days</option></select><select aria-label="Consumption granularity" value={granularity} onChange={(event) => setGranularity(event.target.value as typeof granularity)}><option value="hour">Hour</option><option value="day">Day</option><option value="month">Month</option></select></div>}>{consumption.isLoading ? <LoadingState lines={4} /> : consumption.isError ? <ErrorState title="Consumption unavailable" error={consumption.error} retry={() => consumption.refetch()} /> : <><div className="chart-wrap"><ReactEChartsCore echarts={echarts} option={option} style={{ height: 320, width: '100%' }} opts={{ renderer: 'svg' }} /></div><div className="chart-summary"><div><span>Total</span><strong>{consumption.data?.data.summary.total?.toFixed(1) ?? '—'} {unit ?? 'unknown unit'}</strong></div><div><span>Average</span><strong>{consumption.data?.data.summary.average?.toFixed(1) ?? '—'} {unit ?? 'unknown unit'}</strong></div><div><span>Points</span><strong>{consumption.data?.data.summary.point_count ?? '—'}</strong></div></div></>}</Panel>
      <Panel eyebrow="METER CONTEXT" title="Identity"><div className="context-list"><div><span>Meter ID</span><strong>{item.id}</strong></div><div><span>Network node</span><strong>{item.network_node_id ?? 'not observed'}</strong></div><div><span>Last seen</span><strong>{item.last_seen_at ? new Date(item.last_seen_at).toLocaleString() : 'not observed'}</strong></div><div><span>Source timestamp</span><strong>{item.source_timestamp ?? 'not observed'}</strong></div></div>{anomalies.length > 0 && <div className="signal-note"><CircleAlert size={17} /><p>{anomalies.map((signal) => signal.detail).join(' ')}</p></div>}</Panel>
    </div>
  </div>
}
