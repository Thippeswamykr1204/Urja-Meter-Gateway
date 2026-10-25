import { motion } from 'framer-motion'

export function MetricCard({ label, value, detail, accent = false }: { label: string; value: string; detail: string; accent?: boolean }) {
  return <motion.article className={`metric-card ${accent ? 'metric-accent' : ''}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}><span className="eyebrow">{label}</span><strong>{value}</strong><small>{detail}</small></motion.article>
}
