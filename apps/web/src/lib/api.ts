import type { ApiEnvelope, ConsumptionResponse, HierarchyNode, Meter, ProblemDetails, Signal } from './types'

export type Overview = {
  meter_count: number
  status_counts: Record<string, number>
  load_trend: Array<{ date: string; total: number }>
  signal_count: number
}

export type QualityReport = {
  total_records: number
  issue_count: number
  by_flag: Record<string, number>
  recent_issues: string[]
  examples: Record<string, string[]>
}

export type SyncStatus = {
  status: string
  id?: number
  meters_seen?: number
  readings_seen?: number
  hierarchy_nodes_seen?: number
  error?: string | null
}

export class ApiClientError extends Error {
  status: number
  requestId: string | null
  problem: ProblemDetails | null

  constructor(status: number, problem: ProblemDetails | null, requestId: string | null) {
    super(problem?.detail ?? problem?.title ?? `Request failed (${status})`)
    this.name = 'ApiClientError'
    this.status = status
    this.requestId = requestId
    this.problem = problem
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const problem = await response.json().catch(() => null) as ProblemDetails | null
    throw new ApiClientError(response.status, problem, response.headers.get('X-Request-ID'))
  }
  return response.json() as Promise<T>
}

export const api = {
  overview: () => request<ApiEnvelope<Overview>>('/api/v1/overview'),
  meters: (query = '', pageSize = 25) => request<ApiEnvelope<Meter[]>>(`/api/v1/meters?page=1&page_size=${pageSize}${query}`),
  meterPage: (page: number, pageSize: number, query = '') => request<ApiEnvelope<Meter[]>>(`/api/v1/meters?page=${page}&page_size=${pageSize}${query}`),
  meter: (id: string) => request<ApiEnvelope<Meter>>(`/api/v1/meters/${encodeURIComponent(id)}`),
  consumption: (id: string, query = '') => request<ApiEnvelope<ConsumptionResponse>>(`/api/v1/meters/${encodeURIComponent(id)}/consumption${query}`),
  hierarchy: () => request<ApiEnvelope<HierarchyNode[]>>('/api/v1/hierarchy'),
  quality: () => request<ApiEnvelope<QualityReport>>('/api/v1/quality'),
  signals: () => request<ApiEnvelope<Signal[]>>('/api/v1/insights/signals'),
  sync: () => request<ApiEnvelope<SyncStatus>>('/api/v1/sync/status'),
  refresh: () => request<ApiEnvelope<{ meters_indexed: number }>>('/api/v1/refresh', { method: 'POST' }),
  ready: () => request<{ status: string; portal: Record<string, unknown>; last_sync?: SyncStatus }>('/ready'),
  metrics: () => request<ApiEnvelope<Record<string, unknown>>>('/api/v1/metrics'),
}
