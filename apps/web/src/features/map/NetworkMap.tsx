import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Crosshair, MapPin, Search } from 'lucide-react'
import { api } from '../../lib/api'
import type { Meter } from '../../lib/types'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Panel } from '../../components/Panel'
import { StaleBanner } from '../../components/StaleBanner'
import { StatusPill } from '../../components/StatusPill'
import { useThemeColors } from '../../lib/theme'

function MeterMap({ meters, onSelect }: { meters: Meter[]; onSelect: (meter: Meter) => void }) {
  const mapNode = useRef<HTMLDivElement>(null)
  const colors = useThemeColors()
  useEffect(() => {
    let disposed = false
    let nextMap: import('maplibre-gl').Map | null = null

    const initialize = async () => {
      if (!mapNode.current) return
      const maplibregl = await import('maplibre-gl')
      if (disposed || !mapNode.current) return

      const points = meters.filter((meter) => meter.latitude != null && meter.longitude != null)
      nextMap = new maplibregl.Map({ container: mapNode.current, style: { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': colors['map-background'] } }] }, center: points[0] ? [points[0].longitude!, points[0].latitude!] : [0, 0], zoom: points.length ? 11.5 : 1, attributionControl: false })
      nextMap.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      nextMap.on('load', () => {
        if (!nextMap) return
        nextMap.addSource('basemap', { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© OpenStreetMap contributors' })
        nextMap.addLayer({ id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': Number(colors['map-raster-opacity']) } })
        nextMap.addSource('meters', { type: 'geojson', data: { type: 'FeatureCollection', features: points.map((meter) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [meter.longitude!, meter.latitude!] }, properties: { id: meter.id, status: meter.status ?? 'unknown' } })) }, cluster: true, clusterMaxZoom: 14, clusterRadius: 45 })
        nextMap.addLayer({ id: 'clusters', type: 'circle', source: 'meters', filter: ['has', 'point_count'], paint: { 'circle-color': colors.accent, 'circle-opacity': Number(colors['map-cluster-opacity']), 'circle-radius': ['step', ['get', 'point_count'], 18, 10, 23, 30, 29], 'circle-stroke-color': colors['map-marker-border'], 'circle-stroke-width': 3 } })
        nextMap.addLayer({ id: 'cluster-count', type: 'symbol', source: 'meters', filter: ['has', 'point_count'], layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 11 }, paint: { 'text-color': colors['on-accent'] } })
        nextMap.addLayer({ id: 'unclustered', type: 'circle', source: 'meters', filter: ['!', ['has', 'point_count']], paint: { 'circle-color': ['match', ['get', 'status'], 'warning', colors.warm, 'offline', colors.red, 'unknown', colors.blue, colors.accent], 'circle-radius': 8, 'circle-stroke-color': colors['map-marker-border'], 'circle-stroke-width': 3 } })
        nextMap.on('click', 'clusters', async (event) => {
          if (!nextMap) return
          const feature = nextMap.queryRenderedFeatures(event.point, { layers: ['clusters'] })[0]
          const clusterId = feature.properties?.cluster_id as number
          const zoom = await (nextMap.getSource('meters') as import('maplibre-gl').GeoJSONSource).getClusterExpansionZoom(clusterId)
          nextMap.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom })
        })
        nextMap.on('click', 'unclustered', (event) => {
          if (!nextMap) return
          const feature = nextMap.queryRenderedFeatures(event.point, { layers: ['unclustered'] })[0]
          const selected = points.find((meter) => meter.id === feature.properties?.id)
          if (selected) onSelect(selected)
        })
        for (const layer of ['clusters', 'unclustered']) nextMap.on('mouseenter', layer, () => { if (nextMap) nextMap.getCanvas().style.cursor = 'pointer' })
        for (const layer of ['clusters', 'unclustered']) nextMap.on('mouseleave', layer, () => { if (nextMap) nextMap.getCanvas().style.cursor = '' })
      })
    }

    void initialize()
    return () => {
      disposed = true
      nextMap?.remove()
    }
  }, [colors, meters, onSelect])
  return <div ref={mapNode} className="map-canvas" />
}

export function NetworkMap() {
  const [selected, setSelected] = useState<Meter | null>(null)
  const [radius, setRadius] = useState('')
  const [centerLat, setCenterLat] = useState('')
  const [centerLon, setCenterLon] = useState('')
  const hasRadius = radius !== '' && centerLat !== '' && centerLon !== ''
  const meters = useQuery({ queryKey: ['meters', 'map', radius, centerLat, centerLon], queryFn: () => api.meters(hasRadius ? `&lat=${encodeURIComponent(centerLat)}&lon=${encodeURIComponent(centerLon)}&radius_km=${encodeURIComponent(radius)}` : '', 100) })
  const data = meters.data?.data ?? []
  const located = data.filter((meter) => meter.latitude != null && meter.longitude != null)
  const unknown = data.length - located.length
  return <div className="page-grid"><section className="page-intro compact"><div><span className="eyebrow accent-text">SPATIAL / READ-ONLY</span><h1>Network map</h1><p>Locate indexed meters and inspect their last-known signal. Unknown locations stay visible in the count and never receive invented coordinates.</p></div><div className="map-filters"><label className="search-field"><Crosshair size={16} /><input inputMode="decimal" value={centerLat} onChange={(event) => setCenterLat(event.target.value)} aria-label="Center latitude" placeholder="Latitude" /></label><label className="search-field"><input inputMode="decimal" value={centerLon} onChange={(event) => setCenterLon(event.target.value)} aria-label="Center longitude" placeholder="Longitude" /></label><label className="search-field"><input inputMode="decimal" value={radius} onChange={(event) => setRadius(event.target.value)} aria-label="Radius in kilometers" placeholder="Radius km" /><Search size={14} /></label></div></section><StaleBanner provenance={meters.data?.provenance} /><Panel title="Meter locations" eyebrow={`${data.length} LOCATIONS${unknown ? ` · ${unknown} UNKNOWN LOCATION${unknown === 1 ? '' : 'S'}` : ''}${meters.data?.provenance.stale ? ' · STALE' : ''}`}><div className="map-layout">{meters.isLoading ? <EmptyState title="Loading locations" detail="Reading the indexed coordinates." /> : meters.isError ? <ErrorState title="Map data unavailable" error={meters.error} retry={() => meters.refetch()} /> : data.length === 0 ? <EmptyState title="No locations observed" detail="Choose a radius or index meters with verified coordinates." /> : <><MeterMap meters={data} onSelect={setSelected} />{selected ? <aside className="map-card"><button className="close-card" onClick={() => setSelected(null)} aria-label="Close selected meter">×</button><span className="eyebrow">SELECTED METER</span><h3>{selected.name ?? selected.id}</h3><p className="mono-cell">{selected.id}</p><StatusPill status={selected.status} /><div className="map-card-location"><MapPin size={15} /> {selected.latitude?.toFixed(4)}, {selected.longitude?.toFixed(4)}</div></aside> : <div className="map-legend"><span><i className="legend-dot active" /> active</span><span><i className="legend-dot warning" /> warning</span><span><i className="legend-dot offline" /> offline</span><span><i className="legend-dot unknown" /> unknown</span>{unknown > 0 && <span>{unknown} not mapped</span>}</div>}</>}</div></Panel></div>
}
