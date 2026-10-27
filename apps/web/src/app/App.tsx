import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { LayoutDashboard, ListTree, Map, Menu, Search, ShieldCheck, Sparkles, X } from 'lucide-react'
import { api } from '../lib/api'
import { LoadingState } from '../components/LoadingState'
import { DemoModeBanner } from '../components/DemoModeBanner'
import { ErrorBoundary } from '../components/ErrorBoundary'

const Dashboard = lazy(() => import('../features/dashboard/Dashboard').then((module) => ({ default: module.Dashboard })))
const MeterExplorer = lazy(() => import('../features/meters/MeterExplorer').then((module) => ({ default: module.MeterExplorer })))
const MeterDetail = lazy(() => import('../features/meters/MeterDetail').then((module) => ({ default: module.MeterDetail })))
const NetworkMap = lazy(() => import('../features/map/NetworkMap').then((module) => ({ default: module.NetworkMap })))
const HierarchyExplorer = lazy(() => import('../features/hierarchy/HierarchyExplorer').then((module) => ({ default: module.HierarchyExplorer })))
const QualityPage = lazy(() => import('../features/quality/QualityPage').then((module) => ({ default: module.QualityPage })))

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/meters', label: 'Meter explorer', icon: Search },
  { to: '/map', label: 'Network map', icon: Map },
  { to: '/hierarchy', label: 'Hierarchy', icon: ListTree },
  { to: '/quality', label: 'Data quality', icon: ShieldCheck },
]

export function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => (localStorage.getItem('flock-theme') as 'dark' | 'light' | null) ?? 'dark')
  const [paletteQuery, setPaletteQuery] = useState('')
  const navigate = useNavigate()
  const search = useQuery({ queryKey: ['palette', paletteQuery], queryFn: () => api.meters(`&search=${encodeURIComponent(paletteQuery)}`), enabled: paletteQuery.trim().length > 1 })
  const ready = useQuery({ queryKey: ['ready'], queryFn: api.ready, refetchInterval: 30_000 })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('flock-theme', theme)
  }, [theme])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const go = (path: string) => {
    setPaletteOpen(false)
    setMobileOpen(false)
    navigate(path)
  }

  const filteredNav = useMemo(() => navItems.filter(({ label }) => label.toLowerCase().includes(paletteQuery.toLowerCase())), [paletteQuery])

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
        <div className="brand-lockup">
          <span className="brand-mark"><Sparkles size={16} /></span>
          <div><strong>FLOCK / URJA</strong><span>meter operations</span></div>
        </div>
        <nav aria-label="Primary navigation">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={() => setMobileOpen(false)}>
              <Icon size={17} /> <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer"><span className="live-dot" /> indexed console</div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={20} /></button>
          <div className="breadcrumb"><span>Operations console</span><span className="breadcrumb-divider">/</span><strong>Urja Meter Ops</strong></div>
          <div className="topbar-actions"><button className="theme-button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>{theme === 'dark' ? 'LIGHT' : 'DARK'}</button><button className="command-button" onClick={() => setPaletteOpen(true)}><Search size={16} /><span>Search</span><kbd>⌘ K</kbd></button></div>
        </header>
        <div className="content-wrap"><DemoModeBanner visible={ready.data?.portal?.mode === 'demo' || ready.data?.portal?.configured === false} /><Suspense fallback={<LoadingState lines={6} />}><ErrorBoundary title="This view could not be rendered"><Routes><Route path="/" element={<Dashboard />} /><Route path="/meters" element={<MeterExplorer />} /><Route path="/meters/:meterId" element={<MeterDetail />} /><Route path="/map" element={<NetworkMap />} /><Route path="/hierarchy" element={<HierarchyExplorer />} /><Route path="/quality" element={<QualityPage />} /></Routes></ErrorBoundary></Suspense></div>
      </main>

      <AnimatePresence>{paletteOpen && <motion.div className="palette-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setPaletteOpen(false)}>
        <motion.div className="command-palette" initial={{ opacity: 0, y: -12, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -12 }} onClick={(event) => event.stopPropagation()} role="dialog" aria-label="Command palette">
          <div className="palette-header"><Search size={18} /><input autoFocus value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Jump to a view or meter…" onKeyDown={(event) => { if (event.key === 'Escape') setPaletteOpen(false); if (event.key === 'Enter') go('/meters'); if (event.key === 'ArrowDown') (event.currentTarget.parentElement?.parentElement?.querySelector<HTMLElement>('.palette-item'))?.focus() }} /><button className="icon-button" aria-label="Close command palette" onClick={() => setPaletteOpen(false)}><X size={18} /></button></div>
          <div className="palette-section">Navigate</div>
          {filteredNav.map(({ to, label, icon: Icon }) => <button className="palette-item" key={to} onClick={() => go(to)}><Icon size={16} /><span>{label}</span><span className="palette-arrow">↵</span></button>)}
          {search.data?.data.map((meter) => <button className="palette-item" key={meter.id} onClick={() => go(`/meters/${meter.id}`)}><Search size={16} /><span>{meter.name ?? meter.id}</span><span className="palette-arrow">↵</span></button>)}
        </motion.div>
      </motion.div>}</AnimatePresence>
    </div>
  )
}
