import { fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { expect, test, vi } from 'vitest'
import { MeterExplorer } from './MeterExplorer'
import { api } from '../../lib/api'
import { renderWithQueryClient } from '../../test/test-utils'

vi.mock('../../lib/api', () => ({
  api: {
    meterPage: vi.fn().mockResolvedValue({ data: [{ id: 'MTR-1001', serial_number: 'SER-1001', name: 'North feeder', status: 'active', latitude: null, longitude: null, network_node_id: null, last_seen_at: null, source_timestamp: null, quality: { flags: [], issue_count: 0, notes: [] }, provenance: { source: 'index', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false } }], provenance: { source: 'index', fetched_at: '', indexed_at: null, portal_timestamp: null, stale: false, age_seconds: 0, data_status: 'available', partial: false }, meta: { total: 1, has_next: false } }),
  },
}))

test('explorer syncs search and sort filters to URL', async () => {
  renderWithQueryClient(<MemoryRouter initialEntries={['/meters']}><MeterExplorer /></MemoryRouter>)
  const search = screen.getByRole('textbox', { name: 'Search meters' })
  fireEvent.change(search, { target: { value: 'North' } })
  await waitFor(() => expect(api.meterPage).toHaveBeenCalledWith(1, 25, expect.stringContaining('search=North')))
  await screen.findByText('North feeder')
  fireEvent.click(await screen.findByRole('button', { name: /^Meter$/i }))
  await waitFor(() => expect(api.meterPage).toHaveBeenLastCalledWith(1, 25, expect.stringContaining('sort=name')))
})
