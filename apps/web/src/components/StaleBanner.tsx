import type { Provenance } from '../lib/types'

export function StaleBanner({ provenance }: { provenance?: Provenance | null }) {
  if (!provenance?.stale && !provenance?.partial) return null
  const age = provenance.age_seconds == null ? 'unknown age' : `${Math.round(provenance.age_seconds)} seconds old`
  return <div className="stale-banner" role="status"><strong>{provenance.partial ? 'Partial data' : 'Stale data'}</strong><span>{age}. The last successful indexed snapshot remains visible.</span></div>
}
