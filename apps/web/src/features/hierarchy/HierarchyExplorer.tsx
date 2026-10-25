import { useQuery } from '@tanstack/react-query'
import { hierarchy as d3Hierarchy } from 'd3-hierarchy'
import { ChevronDown, ChevronRight, GitBranch } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../lib/api'
import type { HierarchyNode } from '../../lib/types'
import { EmptyState } from '../../components/EmptyState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'

function TreeNode({ node, depth = 0, maxMeters = 1 }: { node: HierarchyNode; depth?: number; maxMeters?: number }) {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children.length > 0
  return <div className="tree-node"><button className="tree-row" style={{ paddingLeft: `${depth * 22 + 10}px` }} onClick={() => setOpen(!open)} aria-expanded={open}><span className="tree-toggle">{hasChildren ? (open ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : <span />}</span><GitBranch size={14} className="tree-icon" /><span className="tree-label"><strong>{node.name ?? node.id}</strong><small>{node.node_type} · {node.meter_count} meter{node.meter_count === 1 ? '' : 's'}</small><span className="rollup-track"><span style={{ width: `${Math.max(4, (node.meter_count / maxMeters) * 100)}%` }} /></span></span><QualityBadge quality={node.quality} /></button>{open && hasChildren && <div>{node.children.map((child) => <TreeNode key={`${child.id}-${child.record_id ?? ''}`} node={child} depth={depth + 1} maxMeters={maxMeters} />)}</div>}</div>
}

export function HierarchyExplorer() {
  const hierarchy = useQuery({ queryKey: ['hierarchy'], queryFn: api.hierarchy })
  const roots = hierarchy.data?.data ?? []
  const treeCount = roots.reduce((count, root) => count + d3Hierarchy(root).descendants().length, 0)
  const totalMeters = roots.reduce((count, root) => count + root.meter_count, 0)
  return <div className="page-grid"><section className="page-intro compact"><div><span className="eyebrow accent-text">NETWORK / TOPOLOGY</span><h1>Hierarchy explorer</h1><p>Follow the meter from grid root to last-mile signal. Orphans and cycles remain visible as quality flags.</p></div><div className="intro-note">{treeCount} nodes · {totalMeters} meters</div></section><Panel title="Distribution tree" eyebrow={hierarchy.data?.provenance.stale ? 'STALE INDEX' : 'RECONSTRUCTED VIEW'}><div className="tree-wrap">{hierarchy.isLoading ? <LoadingState lines={5} /> : hierarchy.isError ? <div className="error-state"><h2>Hierarchy unavailable</h2><p>{(hierarchy.error as Error).message}</p><button className="button button-ghost" onClick={() => hierarchy.refetch()}>Try again</button></div> : roots.length ? roots.map((root) => <TreeNode key={`${root.id}-${root.record_id ?? ''}`} node={root} maxMeters={Math.max(1, totalMeters)} />) : <EmptyState title="No hierarchy observed" detail="The portal evidence does not currently provide a hierarchy payload." />}</div></Panel></div>
}
