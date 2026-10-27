import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ErrorState } from './ErrorState'
import { StaleBanner } from './StaleBanner'
import { DemoModeBanner } from './DemoModeBanner'
import { DataTrustDrawer } from './DataTrustDrawer'

test('ErrorState shows message and retries', () => {
  const retry = vi.fn()
  render(<ErrorState title="Unavailable" error={new Error('network down')} retry={retry} />)
  expect(screen.getByText('network down')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /try again/i }))
  expect(retry).toHaveBeenCalledOnce()
})

test('StaleBanner is visible only for stale provenance', () => {
  const provenance = { source: 'index', fetched_at: '2026-01-01', indexed_at: null, portal_timestamp: null, age_seconds: 4, stale: true, partial: false, data_status: 'available' }
  const { rerender } = render(<StaleBanner provenance={provenance} />)
  expect(screen.getByRole('status')).toHaveTextContent('Stale data')
  rerender(<StaleBanner provenance={{ ...provenance, stale: false }} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('DemoModeBanner follows visibility', () => {
  const { rerender } = render(<DemoModeBanner visible />)
  expect(screen.getByRole('status')).toHaveTextContent('Demo mode')
  rerender(<DemoModeBanner visible={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

test('DataTrustDrawer opens, closes with escape, and restores focus', () => {
  render(<DataTrustDrawer provenance={{ source: 'demo', fetched_at: '2026-01-01', indexed_at: null, portal_timestamp: null, age_seconds: null, stale: false, partial: false, data_status: 'available' }} quality={{ flags: ['missing'], issue_count: 1, notes: [] }} />)
  const trigger = screen.getByRole('button', { name: 'Data trust' })
  fireEvent.click(trigger)
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getAllByText('Not reported by the portal').length).toBeGreaterThan(0)
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})
