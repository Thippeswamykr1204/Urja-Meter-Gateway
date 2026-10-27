// Generated from openapi.json. Do not edit by hand.

export type ApiEnvelope<T> = { data: T; provenance: Provenance; meta: Record<string, unknown> }

export type QualityFlag = "clean" | "missing" | "invalid" | "duplicate" | "orphan" | "cycle" | "unverified" | "out_of_order" | "negative_value" | "unit_converted" | "assumed_timezone" | "unknown_unit" | "schema_drift" | "ambiguous_number" | "ambiguous_date_format" | "mixed_unit" | "conflict" | "counter_reset" | "partial" | "incompatible_reading"
export const QUALITY_FLAGS = ["clean", "missing", "invalid", "duplicate", "orphan", "cycle", "unverified", "out_of_order", "negative_value", "unit_converted", "assumed_timezone", "unknown_unit", "schema_drift", "ambiguous_number", "ambiguous_date_format", "mixed_unit", "conflict", "counter_reset", "partial", "incompatible_reading"] as const

export type Provenance = {
  source: string;
  fetched_at: string;
  stale: boolean;
  portal_timestamp: string | null;
  age_seconds: number | null;
  indexed_at: string | null;
  data_status: string;
  partial: boolean;
}

export type QualitySummary = {
  flags: Array<QualityFlag>;
  issue_count: number;
  notes: Array<string>;
}

export type Meter = {
  id: string;
  serial_number: string | null;
  name: string | null;
  status: string | null;
  latitude: number | null;
  longitude: number | null;
  network_node_id: string | null;
  last_seen_at: string | null;
  source_timestamp: string | null;
  quality: QualitySummary;
  provenance: Provenance;
}

export type ConsumptionPoint = {
  timestamp: string | null;
  original_timestamp: string | null;
  value: number | null;
  unit: string | null;
  original_value: number | null;
  original_unit: string | null;
  reading_kind: string;
  quality: QualitySummary;
}

export type ConsumptionSummary = {
  total: number | null;
  average: number | null;
  minimum: number | null;
  maximum: number | null;
  point_count: number;
  missing_count: number;
  unit: string | null;
  mixed_units: boolean;
  invalid_count: number;
  unknown_unit_count: number;
  counter_reset_count: number;
  reading_kind: string;
  complete: boolean;
}

export type ConsumptionResponse = {
  meter_id: string;
  granularity: string;
  points: Array<ConsumptionPoint>;
  summary: ConsumptionSummary;
  provenance: Provenance;
  quality: QualitySummary;
}

export type HierarchyNode = {
  id: string;
  record_id: string | null;
  name: string | null;
  node_type: string;
  parent_id: string | null;
  meter_count: number;
  consumption_total: number | null;
  consumption_unit: string | null;
  consumption_share: number | null;
  missing_reading_count: number;
  mixed_units: boolean;
  quality: QualitySummary;
  children: Array<HierarchyNode>;
}

export type DataQualityReport = {
  generated_at: string;
  total_records: number;
  issue_count: number;
  by_flag: Record<string, number>;
  recent_issues: Array<string>;
  examples: Record<string, Array<string>>;
}

export type SyncRun = {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  meters_seen: number;
  readings_seen: number;
  hierarchy_nodes_seen: number;
  error: string | null;
  duration_seconds: number | null;
  records_rejected: number;
  portal_latency_seconds: number | null;
  checkpoint: string | null;
  partial: boolean;
}

export type Signal = {
  meter_id: string;
  kind: string;
  timestamp: string | null;
  detail: string;
  severity: string;
  observed_value: number | null;
  baseline: number | null;
  rule: string | null;
  sufficient_history: boolean;
}

export type ProblemDetails = { type?: string; title?: string; status?: number; detail?: string; code?: string; request_id?: string }
