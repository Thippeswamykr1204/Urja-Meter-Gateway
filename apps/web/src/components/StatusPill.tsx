export function StatusPill({ status }: { status: string | null }) {
  const value = status ?? 'unknown'
  return <span className={`status-pill status-${value.toLowerCase()}`}><span />{value}</span>
}
