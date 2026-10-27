import { renderHook } from '@testing-library/react'
import { useReducedMotionPreference } from './useMotion'
import { expect, test, vi } from 'vitest'

test('reduced motion preference disables motion', () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  const { result } = renderHook(() => useReducedMotionPreference())
  expect(result.current).toBe(true)
})
