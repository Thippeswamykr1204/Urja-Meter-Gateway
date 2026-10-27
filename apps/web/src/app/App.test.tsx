import { fireEvent, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'
import { App } from './App'
import { renderWithQueryClient } from '../test/test-utils'

vi.mock('../lib/api', () => ({
  api: {
    ready: vi.fn().mockResolvedValue({ status: 'ready', portal: { mode: 'demo', configured: false } }),
    meters: vi.fn().mockResolvedValue({ data: [], provenance: { source: 'demo', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: {} }),
    meterPage: vi.fn().mockResolvedValue({ data: [], provenance: { source: 'demo', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: { total: 0, has_next: false } }),
    overview: vi.fn().mockResolvedValue({ data: { meter_count: 0, status_counts: {}, load_trend: [], signal_count: 0 }, provenance: { source: 'demo', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: {} }),
    quality: vi.fn().mockResolvedValue({ data: { total_records: 0, issue_count: 0, by_flag: {}, recent_issues: [], examples: {} }, provenance: { source: 'demo', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: {} }),
    sync: vi.fn().mockResolvedValue({ data: { status: 'idle' }, provenance: { source: 'demo', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: {} }),
  },
  ApiClientError: class ApiClientError extends Error {},
}))

test('command palette accepts Enter and ArrowDown keyboard navigation', async () => {
  renderWithQueryClient(<MemoryRouter><App /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: /search/i }))
  const input = await screen.findByPlaceholderText(/jump to a view/i)
  fireEvent.keyDown(input, { key: 'ArrowDown' })
  expect(screen.getByRole('button', { name: /overview/i })).toHaveFocus()
  fireEvent.keyDown(input, { key: 'Enter' })
  expect(await screen.findByRole('heading', { name: /meter explorer/i })).toBeInTheDocument()
})
