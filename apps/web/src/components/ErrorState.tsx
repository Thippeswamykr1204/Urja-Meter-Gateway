import { AlertCircle, RefreshCw } from 'lucide-react'
import { ApiClientError } from '../lib/api'

function errorDetails(error: unknown): { detail: string; requestId: string | null } {
  if (error instanceof ApiClientError) {
    return { detail: error.message, requestId: error.requestId ?? error.problem?.request_id ?? null }
  }
  if (error instanceof Error) return { detail: error.message, requestId: null }
  return { detail: 'The request could not be completed.', requestId: null }
}

export function ErrorState({ title = 'Data unavailable', error, retry }: { title?: string; error: unknown; retry?: () => void }) {
  const details = errorDetails(error)
  return <div className="error-state" role="alert"><AlertCircle size={22} /><h2>{title}</h2><p>{details.detail}</p>{details.requestId && <small className="mono-cell">Request ID: {details.requestId}</small>}{retry && <button className="button button-ghost" onClick={retry}><RefreshCw size={15} /> Try again</button>}</div>
}
