import { motion } from 'framer-motion'
import { useReducedMotionPreference } from '../lib/useMotion'

export function MetricCard({ label, value, detail, accent = false }: { label: string; value: string; detail: string; accent?: boolean }) {
  const reduced = useReducedMotionPreference()
  return <motion.article className={`metric-card ${accent ? 'metric-accent' : ''}`} initial={reduced ? false : { opacity: 0, y: 8 }} animate={reduced ? undefined : { opacity: 1, y: 0 }} transition={reduced ? { duration: 0 } : { duration: 0.22 }}><span className="eyebrow">{label}</span><strong>{value}</strong><small>{detail}</small></motion.article>
}
