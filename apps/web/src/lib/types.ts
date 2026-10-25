export type QualityFlag = 'clean' | 'missing' | 'invalid' | 'duplicate' | 'orphan' | 'cycle' | 'unverified' | 'out_of_order' | 'negative_value' | 'unit_converted' | 'assumed_timezone' | 'unknown_unit' | 'schema_drift' | 'ambiguous_number' | 'ambiguous_date_format'

export type Provenance = {
  source: string
  fetched_at: string
  stale: boolean
  age_seconds?: number | null
  portal_timestamp?: string | null
}

export type QualitySummary = {
  flags: QualityFlag[]
  issue_count: number
  notes: string[]
}

export type Meter = {
  id: string
  serial_number: string | null
  name: string | null
  status: string | null
  latitude: number | null
  longitude: number | null
  network_node_id: string | null
  last_seen_at: string | null
  quality: QualitySummary
  provenance: Provenance
}

export type ConsumptionPoint = {
  timestamp: string | null
  original_timestamp: string | null
  value: number | null
  unit: string | null
  original_value?: number | null
  original_unit?: string | null
  quality: QualitySummary
}

export type ApiEnvelope<T> = { data: T; provenance: Provenance; meta: Record<string, unknown> }

export type HierarchyNode = {
  id: string
  record_id?: string | null
  name: string | null
  node_type: string
  parent_id: string | null
  meter_count: number
  consumption_total: number | null
  quality: QualitySummary
  children: HierarchyNode[]
}
