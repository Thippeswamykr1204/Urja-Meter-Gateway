import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import maplibregl from 'maplibre-gl'
import { Crosshair, MapPin, Search } from 'lucide-react'
import { api } from '../../lib/api'
import type { Meter } from '../../lib/types'
import { Panel } from '../../components/Panel'
import { StatusPill } from '../../components/StatusPill'

function MeterMap({ meters, onSelect }: { meters: Meter[]; onSelect: (meter: Meter) => void }) {
  const mapNode = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  useEffect(() => {
    if (!mapNode.current) return
    const points = meters.filter((meter) => meter.latitude != null && meter.longitude != null)
    const nextMap = new maplibregl.Map({ container: mapNode.current, style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#161d14' } }] }, center: [77.605, 12.96], zoom: 11.5, attributionControl: false })
    map.current = nextMap
    nextMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    nextMap.on('load', () => {
      nextMap.addSource('meters', { type: 'geojson', data: { type: 'FeatureCollection', features: points.map((meter) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [meter.longitude!, meter.latitude!] }, properties: { id: meter.id, status: meter.status ?? 'unknown' } })), }, cluster: true, clusterMaxZoom: 14, clusterRadius: 45 })
      nextMap.addLayer({ id: 'clusters', type: 'circle', source: 'meters', filter: ['has', 'point_count'], paint: { 'circle-color': '#d9f26d', 'circle-opacity': 0.82, 'circle-radius': ['step', ['get', 'point_count'], 18, 10, 23, 30, 29], 'circle-stroke-color': '#11140f', 'circle-stroke-width': 3 } })
      nextMap.addLayer({ id: 'cluster-count', type: 'symbol', source: 'meters', filter: ['has', 'point_count'], layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 11 }, paint: { 'text-color': '#11140f' } })
      nextMap.addLayer({ id: 'unclustered', type: 'circle', source: 'meters', filter: ['!', ['has', 'point_count']], paint: { 'circle-color': ['match', ['get', 'status'], 'warning', '#f2b56d', 'offline', '#f0776d', '#d9f26d'], 'circle-radius': 8, 'circle-stroke-color': '#11140f', 'circle-stroke-width': 3 } })
      nextMap.on('click', 'clusters', async (event) => {
        const feature = nextMap.queryRenderedFeatures(event.point, { layers: ['clusters'] })[0]
        const clusterId = feature.properties?.cluster_id as number
        const zoom = await (nextMap.getSource('meters') as maplibregl.GeoJSONSource).getClusterExpansionZoom(clusterId)
        nextMap.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom })
      })
      nextMap.on('click', 'unclustered', (event) => {
        const feature = nextMap.queryRenderedFeatures(event.point, { layers: ['unclustered'] })[0]
        const selected = points.find((meter) => meter.id === feature.properties?.id)
        if (selected) onSelect(selected)
      })
      for (const layer of ['clusters', 'unclustered']) nextMap.on('mouseenter', layer, () => { nextMap.getCanvas().style.cursor = 'pointer' })
      for (const layer of ['clusters', 'unclustered']) nextMap.on('mouseleave', layer, () => { nextMap.getCanvas().style.cursor = '' })
    })
    return () => nextMap.remove()
  }, [meters, onSelect])
  return <div ref={mapNode} className="map-canvas" />
}

export function NetworkMap() {
  const [selected, setSelected] = useState<Meter | null>(null)
  const [radius, setRadius] = useState('')
  const [centerLat, setCenterLat] = useState('12.96')
  const [centerLon, setCenterLon] = useState('77.60')
  const hasRadius = radius && centerLat && centerLon
  const meters = useQuery({ queryKey: ['meters', 'map', radius, centerLat, centerLon], queryFn: () => api.meters(hasRadius ? `&lat=${centerLat}&lon=${centerLon}&radius_km=${radius}` : '', 100) })
  return <div className="page-grid"><section className="page-intro compact"><div><span className="eyebrow accent-text">SPATIAL / READ-ONLY</span><h1>Network map</h1><p>Locate indexed meters and inspect their last-known signal.</p></div><div className="map-filters"><label className="search-field"><Crosshair size={16} /><input inputMode="decimal" value={centerLat} onChange={(event) => setCenterLat(event.target.value)} aria-label="Center latitude" placeholder="Latitude" /></label><label className="search-field"><input inputMode="decimal" value={centerLon} onChange={(event) => setCenterLon(event.target.value)} aria-label="Center longitude" placeholder="Longitude" /></label><label className="search-field"><input inputMode="decimal" value={radius} onChange={(event) => setRadius(event.target.value)} aria-label="Radius in kilometers" placeholder="Radius km" /><Search size={14} /></label></div></section><Panel title="Meter locations" eyebrow={`${meters.data?.data.length ?? 0} LOCATIONS${meters.data?.provenance.stale ? ' · STALE' : ''}`}><div className="map-layout">{meters.isError ? <div className="error-state"><h2>Map data unavailable</h2><p>{(meters.error as Error).message}</p><button className="button button-ghost" onClick={() => meters.refetch()}>Try again</button></div> : <MeterMap meters={meters.data?.data ?? []} onSelect={setSelected} />}{selected ? <aside className="map-card"><button className="close-card" onClick={() => setSelected(null)}>×</button><span className="eyebrow">SELECTED METER</span><h3>{selected.name ?? selected.id}</h3><p className="mono-cell">{selected.id}</p><StatusPill status={selected.status} /><div className="map-card-location"><MapPin size={15} /> {selected.latitude?.toFixed(4)}, {selected.longitude?.toFixed(4)}</div></aside> : <div className="map-legend"><span><i className="legend-dot active" /> active</span><span><i className="legend-dot warning" /> warning</span><span><i className="legend-dot offline" /> offline</span></div>}</div></Panel></div>
}
