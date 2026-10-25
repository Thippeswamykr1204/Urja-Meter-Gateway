import type { QualitySummary } from '../lib/types'

export function QualityBadge({ quality }: { quality: QualitySummary }) {
  const label = quality.issue_count ? `${quality.issue_count} issue${quality.issue_count === 1 ? '' : 's'}` : 'clean'
  return <span className={`quality-badge ${quality.issue_count ? 'quality-warning' : ''}`} title={quality.notes.join(' · ')}>{label}</span>
}
