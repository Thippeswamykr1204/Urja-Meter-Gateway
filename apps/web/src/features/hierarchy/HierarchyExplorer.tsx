import { useQuery } from '@tanstack/react-query'
import { hierarchy as d3Hierarchy, tree as d3Tree, type HierarchyPointNode } from 'd3-hierarchy'
import { ChevronDown, ChevronRight, GitBranch } from 'lucide-react'
import { useMemo, useState } from 'react'
import { DataTrustDrawer } from '../../components/DataTrustDrawer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { Panel } from '../../components/Panel'
import { QualityBadge } from '../../components/QualityBadge'
import { StaleBanner } from '../../components/StaleBanner'
import { api } from '../../lib/api'
import type { HierarchyNode as ApiHierarchyNode } from '../../lib/types'

function hasFlag(node: ApiHierarchyNode, flag: string) {
  return node.quality.flags.includes(flag as ApiHierarchyNode['quality']['flags'][number])
}

function nodeClassName(node: ApiHierarchyNode) {
  const flags = node.quality.flags
  if (flags.includes('cycle')) return 'hierarchy-node hierarchy-node-cycle'
  if (flags.includes('orphan')) return 'hierarchy-node hierarchy-node-orphan'
  if (flags.includes('duplicate')) return 'hierarchy-node hierarchy-node-duplicate'
  if (flags.length || node.mixed_units) return 'hierarchy-node hierarchy-node-warning'
  return 'hierarchy-node'
}

export function TreeNode({ node, depth = 0, maxMeters = 1 }: { node: ApiHierarchyNode; depth?: number; maxMeters?: number }) {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children.length > 0
  const share = node.consumption_share ?? (node.meter_count / maxMeters)

  return (
    <div className="tree-node">
      <div
        className={`tree-row ${nodeClassName(node)}`}
        style={{ paddingLeft: `${depth * 22 + 10}px` }}
        role="button"
        tabIndex={0}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowRight' && hasChildren) {
            event.preventDefault()
            setOpen(true)
          }
          if (event.key === 'ArrowLeft' && hasChildren) {
            event.preventDefault()
            setOpen(false)
          }
        }}
        aria-expanded={hasChildren ? open : undefined}
      >
        <span className="tree-toggle">{hasChildren ? (open ? <ChevronDown size={15} /> : <ChevronRight size={15} />) : <span />}</span>
        <GitBranch size={14} className="tree-icon" />
        <span className="tree-label">
          <strong>{node.name ?? node.id}</strong>
          <small>
            {node.node_type} · {node.meter_count} meter{node.meter_count === 1 ? '' : 's'} · {node.missing_reading_count} missing readings
            {node.mixed_units ? ' · mixed units' : ''}
            {hasFlag(node, 'orphan') ? ' · orphan' : ''}
            {hasFlag(node, 'cycle') ? ' · cycle' : ''}
            {hasFlag(node, 'duplicate') ? ' · duplicate' : ''}
          </small>
          <span className="rollup-track" aria-label={`${Math.round(share * 100)} percent rollup share`}>
            <span style={{ width: `${Math.max(4, Math.min(100, share * 100))}%` }} />
          </span>
        </span>
        <QualityBadge quality={node.quality} />
        <DataTrustDrawer quality={node.quality} label={`Trust for ${node.name ?? node.id}`} />
      </div>
      {open && hasChildren && <div>{node.children.map((child) => <TreeNode key={`${child.id}-${child.record_id ?? ''}`} node={child} depth={depth + 1} maxMeters={maxMeters} />)}</div>}
    </div>
  )
}

function LayoutTree({ roots }: { roots: ApiHierarchyNode[] }) {
  const layouts = useMemo(() => roots.map((root) => {
    const treeRoot = d3Hierarchy<ApiHierarchyNode>(root)
    const layout = d3Tree<ApiHierarchyNode>().nodeSize([58, 184])
    return layout(treeRoot)
  }), [roots])

  if (!layouts.length) return null

  return (
    <div className="hierarchy-layout" aria-label="Hierarchy layout">
      {layouts.map((root, index) => {
        const nodes = root.descendants()
        const links = root.links()
        const minX = Math.min(...nodes.map((node) => node.x))
        const maxX = Math.max(...nodes.map((node) => node.x))
        const minY = Math.min(...nodes.map((node) => node.y))
        const maxY = Math.max(...nodes.map((node) => node.y))
        const contentWidth = maxY - minY + 210
        const width = Math.max(620, contentWidth)
        const height = Math.max(150, root.height * 70 + 90)
        const offsetX = (width - contentWidth) / 2 - minY
        const offsetY = (height - (maxX - minX)) / 2 - minX

        return (
          <svg key={`${root.data.id}-${index}`} className="hierarchy-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${root.data.name ?? root.data.id} hierarchy layout`}>
            <g transform={`translate(${offsetX}, ${offsetY})`}>
              {links.map((link) => <path key={`${link.source.data.id}-${link.target.data.id}`} className="hierarchy-link" d={`M${link.source.y},${link.source.x}C${(link.source.y + link.target.y) / 2},${link.source.x} ${(link.source.y + link.target.y) / 2},${link.target.x} ${link.target.y},${link.target.x}`} />)}
              {nodes.map((node: HierarchyPointNode<ApiHierarchyNode>) => (
                <g key={`${node.data.id}-${node.data.record_id ?? ''}`} className={nodeClassName(node.data)} transform={`translate(${node.y}, ${node.x})`}>
                  <title>{`${node.data.name ?? node.data.id}: ${node.data.meter_count} meters${node.data.mixed_units ? ', mixed units' : ''}`}</title>
                  <circle r={node.data.node_type === 'meter' ? 6 : 9} />
                  <text x={node.data.name === 'North substation' || node.data.name === 'South substation' ? 0 : node.data.name === 'Distribution grid' ? 40 : 15} y={node.data.name === 'North substation' || node.data.name === 'South substation' ? -12 : 4} textAnchor={node.data.name === 'North substation' || node.data.name === 'South substation' ? 'middle' : undefined}>{node.data.name ?? node.data.id}</text>
                </g>
              ))}
            </g>
          </svg>
        )
      })}
    </div>
  )
}

export function HierarchyExplorer() {
  const hierarchy = useQuery({ queryKey: ['hierarchy'], queryFn: api.hierarchy })
  const roots = hierarchy.data?.data ?? []
  const treeCount = roots.reduce((count, root) => count + d3Hierarchy(root).descendants().length, 0)
  const totalMeters = roots.reduce((count, root) => count + root.meter_count, 0)

  return (
    <div className="page-grid">
      <section className="page-intro compact">
        <div>
          <span className="eyebrow accent-text">NETWORK / TOPOLOGY</span>
          <h1>Hierarchy explorer</h1>
          <p>Follow the meter from grid root to last-mile signal. Orphans, cycles, duplicates, mixed units, and missing readings remain visible.</p>
        </div>
        <div className="intro-note">{treeCount} nodes · {totalMeters} meters</div>
      </section>
      <StaleBanner provenance={hierarchy.data?.provenance} />
      <Panel title="Distribution layout" eyebrow={hierarchy.data?.provenance.stale ? 'STALE INDEX' : 'D3 RECONSTRUCTED VIEW'}>
        {hierarchy.isLoading ? <LoadingState lines={5} /> : hierarchy.isError ? <ErrorState title="Hierarchy unavailable" error={hierarchy.error} retry={() => hierarchy.refetch()} /> : roots.length ? <LayoutTree roots={roots} /> : <EmptyState title="No hierarchy observed" detail="The portal configuration does not currently provide a hierarchy payload." />}
      </Panel>
      <Panel title="Accessible tree" eyebrow="KEYBOARD NAVIGATION">
        <div className="tree-wrap">
          {hierarchy.isLoading ? <LoadingState lines={5} /> : hierarchy.isError ? <ErrorState title="Hierarchy unavailable" error={hierarchy.error} retry={() => hierarchy.refetch()} /> : roots.length ? roots.map((root) => <TreeNode key={`${root.id}-${root.record_id ?? ''}`} node={root} maxMeters={Math.max(1, totalMeters)} />) : <EmptyState title="No hierarchy observed" detail="The portal configuration does not currently provide a hierarchy payload." />}
        </div>
      </Panel>
    </div>
  )
}
