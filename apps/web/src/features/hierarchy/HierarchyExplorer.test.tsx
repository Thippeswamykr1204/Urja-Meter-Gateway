import { fireEvent, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { TreeNode } from './HierarchyExplorer'
import { renderWithQueryClient } from '../../test/test-utils'

test('hierarchy tree expands and collapses with keyboard arrows', () => {
  const node = { id: 'root', record_id: null, name: 'Root', node_type: 'root', parent_id: null, meter_count: 1, consumption_total: null, consumption_unit: null, consumption_share: null, missing_reading_count: 0, mixed_units: false, quality: { flags: [], issue_count: 0, notes: [] }, children: [{ id: 'child', record_id: null, name: 'Child', node_type: 'meter', parent_id: 'root', meter_count: 1, consumption_total: null, consumption_unit: null, consumption_share: null, missing_reading_count: 0, mixed_units: false, quality: { flags: [], issue_count: 0, notes: [] }, children: [] }] }
  renderWithQueryClient(<TreeNode node={node} />)
  const row = screen.getByText('Root').closest('[role="button"]') as HTMLElement
  expect(row).toHaveAttribute('aria-expanded', 'true')
  fireEvent.keyDown(row, { key: 'ArrowLeft' })
  expect(row).toHaveAttribute('aria-expanded', 'false')
  fireEvent.keyDown(row, { key: 'ArrowRight' })
  expect(row).toHaveAttribute('aria-expanded', 'true')
})
