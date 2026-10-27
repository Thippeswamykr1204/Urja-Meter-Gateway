import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions, type RenderResult } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export function renderWithQueryClient(
  element: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>,
): RenderResult {
  const client = createTestQueryClient()
  return render(
    <QueryClientProvider client={client}>
      {element as ReactNode}
    </QueryClientProvider>,
    options,
  )
}
