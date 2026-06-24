// ====== Code Summary ======
// <IRNavigator> — heading-tree + block explorer for a parsed DocumentIR.
//
// Two-pane layout:
//   • Left rail   — collapsible heading hierarchy (H1 > H2 > H3) built from the
//                   blocks of every page.  Counts per node (n blocks / n figures
//                   / n tables) shown inline.  Click a heading to focus its section.
//   • Right panel — every block under the selected heading with rich detail
//                   (text / figure crop / table cells / chain traces) and a search
//                   filter (text + type).
//
// Pages are fetched lazily and cached in component state — each page is at most
// one round-trip even when the user expands many sections.

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { BlockInfo, Document } from '../../api/types'
import { getBlockFigure, getPage, listPages } from '../../api/client'

interface Props {
  doc: Document
  collectionId: string
}

interface FlatBlock extends BlockInfo {
  /** 1-based block index within reading order, useful for stable keys. */
  idx: number
}

interface HeadingNode {
  id: string
  text: string
  level: number
  page: number
  // Reading-order index of the heading block itself.
  blockIdx: number
  children: HeadingNode[]
  // Blocks that belong to this section (excluding the heading itself), in reading order.
  blocks: FlatBlock[]
  // Counts cached for the sidebar.
  nBlocks: number
  nFigures: number
  nTables: number
}

// Sentinel section that holds blocks appearing BEFORE any heading.
const ROOT_ID = '__root__'

export function IRNavigator({ doc, collectionId }: Props) {
  const [allBlocks, setAllBlocks] = useState<FlatBlock[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string>(ROOT_ID)
  const [expanded, setExpanded] = useState<Set<string>>(new Set([ROOT_ID]))
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [figureSrcs, setFigureSrcs] = useState<Record<string, string>>({})

  // ── Load all blocks (one fetch per page, parallelised) ─────────────────────
  useEffect(() => {
    if (doc.status !== 'done') return
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const pages = await listPages(collectionId, doc.id)
        const pageDetails = await Promise.all(
          pages.pages.map(p => getPage(collectionId, doc.id, p.page))
        )
        if (cancelled) return
        let idx = 0
        const flat: FlatBlock[] = []
        for (const pd of pageDetails) {
          for (const b of pd.blocks) {
            flat.push({ ...b, idx: idx++ })
          }
        }
        setAllBlocks(flat)
      } catch (err) {
        if (!cancelled) setError(String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [doc.id, doc.status, collectionId])

  // ── Build the heading tree from flat blocks ────────────────────────────────
  const tree = useMemo(() => buildHeadingTree(allBlocks), [allBlocks])
  const flatNodes = useMemo(() => flattenTree(tree), [tree])
  const nodeIndex = useMemo(() => {
    const m = new Map<string, HeadingNode>()
    flatNodes.forEach(n => m.set(n.id, n))
    return m
  }, [flatNodes])

  const selected = nodeIndex.get(selectedId) ?? tree

  // ── Fetch figure crops only for visible figure blocks ──────────────────────
  const visibleFigureIds = useMemo(
    () => selected.blocks.filter(b => b.type.toLowerCase() === 'figure').map(b => b.id),
    [selected],
  )
  useEffect(() => {
    visibleFigureIds.forEach(async (bid) => {
      if (figureSrcs[bid] !== undefined) return
      try {
        const r = await getBlockFigure(collectionId, doc.id, bid)
        setFigureSrcs(prev => ({ ...prev, [bid]: r.url }))
      } catch {
        setFigureSrcs(prev => ({ ...prev, [bid]: '' }))
      }
    })
  }, [visibleFigureIds, collectionId, doc.id])

  // ── Apply search + type filter to the selected section's blocks ────────────
  const filteredBlocks = useMemo(() => {
    const q = search.trim().toLowerCase()
    return selected.blocks.filter(b => {
      if (typeFilter !== 'all' && b.type.toLowerCase() !== typeFilter) return false
      if (!q) return true
      const text = (b.text ?? '').toLowerCase()
      return text.includes(q) || b.id.toLowerCase().includes(q)
    })
  }, [selected, search, typeFilter])

  const toggleExpand = useCallback((id: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  // ── Render ─────────────────────────────────────────────────────────────────
  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12, padding: 12 }}>
        {doc.status === 'running' || doc.status === 'pending'
          ? 'Parsing in progress…'
          : 'No IR available (document not done).'}
      </div>
    )
  }
  if (loading) return <div className="text-muted" style={{ padding: 12 }}><span className="spin">⟳</span> Loading IR…</div>
  if (error) return <div className="error-banner">{error}</div>
  if (allBlocks.length === 0) return <div className="text-dim" style={{ padding: 12 }}>No blocks in the IR.</div>

  return (
    <div className="ir-nav">
      {/* ── Left rail: heading tree ── */}
      <aside className="ir-nav-tree">
        <div className="ir-nav-tree-header">Structure</div>
        <TreeNode
          node={tree}
          depth={0}
          expanded={expanded}
          onToggle={toggleExpand}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </aside>

      {/* ── Right panel: filters + blocks ── */}
      <div className="ir-nav-detail">
        <div className="ir-nav-detail-header">
          <div className="ir-nav-detail-title" title={selected.text || 'Pre-heading blocks'}>
            {selected.level > 0 && <span className="ir-nav-detail-level mono">H{selected.level}</span>}
            <span>{selected.text || '(pre-heading)'}</span>
          </div>
          <div className="ir-nav-detail-stats">
            <span className="text-dim">{selected.nBlocks} blocks</span>
            {selected.nFigures > 0 && <span className="text-dim">· {selected.nFigures} fig</span>}
            {selected.nTables > 0 && <span className="text-dim">· {selected.nTables} tbl</span>}
          </div>
        </div>

        <div className="ir-nav-filters">
          <input
            className="input"
            type="text"
            placeholder="Search text or block id…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{ flex: 1, fontSize: 12 }}
          />
          <select
            className="input select"
            value={typeFilter}
            onChange={e => setTypeFilter(e.target.value)}
            style={{ width: 130, fontSize: 12 }}
          >
            <option value="all">All types</option>
            <option value="paragraph">Paragraph</option>
            <option value="heading">Heading</option>
            <option value="list_item">List item</option>
            <option value="figure">Figure</option>
            <option value="table">Table</option>
            <option value="caption">Caption</option>
            <option value="code">Code</option>
            <option value="formula">Formula</option>
            <option value="header_footer">Header / footer</option>
          </select>
        </div>

        <div className="ir-nav-blocks">
          {filteredBlocks.length === 0 && (
            <div className="text-dim" style={{ fontSize: 11, padding: 12 }}>
              No blocks match the current filter.
            </div>
          )}
          {filteredBlocks.map(b => (
            <BlockCard key={b.id} block={b} figureSrc={figureSrcs[b.id]} />
          ))}
        </div>
      </div>
    </div>
  )
}

// ── TreeNode (recursive) ────────────────────────────────────────────────────

function TreeNode({
  node, depth, expanded, onToggle, selectedId, onSelect,
}: {
  node: HeadingNode
  depth: number
  expanded: Set<string>
  onToggle: (id: string) => void
  selectedId: string
  onSelect: (id: string) => void
}) {
  const isOpen = expanded.has(node.id)
  const hasKids = node.children.length > 0
  const isSelected = node.id === selectedId
  return (
    <div>
      <div
        className={`ir-nav-tree-row ${isSelected ? 'ir-nav-tree-row-active' : ''}`}
        style={{ paddingLeft: 8 + depth * 12 }}
      >
        <span
          className="ir-nav-tree-toggle"
          onClick={() => hasKids && onToggle(node.id)}
          style={{ opacity: hasKids ? 1 : 0 }}
        >{isOpen ? '▾' : '▸'}</span>
        {node.level > 0 && (
          <span className="ir-nav-tree-level mono">H{node.level}</span>
        )}
        <span
          className="ir-nav-tree-label"
          onClick={() => onSelect(node.id)}
          title={node.text}
        >
          {node.text || '(pre-heading)'}
        </span>
        <span className="ir-nav-tree-count text-dim">{node.nBlocks}</span>
      </div>
      {isOpen && node.children.map(c => (
        <TreeNode
          key={c.id}
          node={c}
          depth={depth + 1}
          expanded={expanded}
          onToggle={onToggle}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  )
}

// ── BlockCard — rich detail for one block ───────────────────────────────────

function BlockCard({ block, figureSrc }: { block: FlatBlock; figureSrc: string | undefined }) {
  const [open, setOpen] = useState(false)
  const colour = blockTypeColor(block.type)
  const isFigure = block.type.toLowerCase() === 'figure'
  const isTable = block.type.toLowerCase() === 'table'
  const td = block.type_data as Record<string, unknown> | null | undefined

  return (
    <div className="ir-block-card">
      <div className="ir-block-card-header" onClick={() => setOpen(o => !o)}>
        <span className="tag" style={{
          color: colour, borderColor: colour + '40', background: colour + '15',
          fontSize: 9, padding: '1px 6px',
        }}>{block.type}</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>p.{block.page + 1}</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>{block.id.slice(0, 16)}…</span>
        {isFigure && td?.kind != null && (
          <span className="tag" style={{ fontSize: 9, padding: '1px 5px' }}>{String(td.kind)}</span>
        )}
        <span className="ir-block-card-preview text-muted">
          {block.text ? block.text.slice(0, 130) : isFigure ? '(figure)' : isTable ? '(table)' : ''}
        </span>
        <span className="text-dim" style={{ fontSize: 10 }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="ir-block-card-body fadein">
          {block.bbox.length === 4 && (
            <div className="ir-block-card-row">
              <span className="ir-block-card-label">bbox</span>
              <span className="mono" style={{ fontSize: 10 }}>
                [{block.bbox.map(v => v.toFixed(3)).join(', ')}]
              </span>
            </div>
          )}

          {block.text && (
            <div className="ir-block-card-row" style={{ alignItems: 'flex-start' }}>
              <span className="ir-block-card-label">text</span>
              <pre className="ir-block-card-text">{block.text}</pre>
            </div>
          )}

          {isFigure && (
            <div className="ir-block-card-row" style={{ alignItems: 'flex-start' }}>
              <span className="ir-block-card-label">crop</span>
              <div style={{ flex: 1 }}>
                {figureSrc ? (
                  <img
                    src={figureSrc}
                    alt={`Figure ${block.id}`}
                    loading="lazy"
                    style={{ maxWidth: 320, maxHeight: 320, border: '1px solid var(--border)', borderRadius: 4 }}
                  />
                ) : figureSrc === '' ? (
                  <span className="text-dim" style={{ fontSize: 10 }}>crop not available</span>
                ) : (
                  <span className="text-dim" style={{ fontSize: 10 }}><span className="spin">⟳</span> loading…</span>
                )}
              </div>
            </div>
          )}

          {isFigure && td && (
            <>
              {td.kind != null && <KvRow k="kind" v={String(td.kind)} />}
              {td.relevance != null && <KvRow k="relevance" v={Number(td.relevance).toFixed(3)} />}
              {td.ocr_text != null && <KvRow k="ocr_text" v={String(td.ocr_text)} multi />}
              {td.description != null && <KvRow k="description" v={String(td.description)} multi />}
              {Array.isArray(td.data_table) && (
                <KvRow k="data_table" v={`${(td.data_table as string[][]).length} rows × ${(td.data_table as string[][])[0]?.length ?? 0} cols`} />
              )}
            </>
          )}

          {isTable && td && (
            <KvRow k="table" v={`${(td.n_rows as number | undefined) ?? '?'} × ${(td.n_cols as number | undefined) ?? '?'}`} />
          )}

          {block.chain_traces && block.chain_traces.length > 0 && (
            <div className="ir-block-card-row" style={{ alignItems: 'flex-start' }}>
              <span className="ir-block-card-label">chain traces</span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {block.chain_traces.map((t, i) => {
                  const n = t.attempts?.length ?? 0
                  return (
                    <span key={i} className="mono text-dim" style={{ fontSize: 10 }}>
                      {t.stage} → {t.final_provider ?? '(exhausted)'} · {n} attempt{n !== 1 ? 's' : ''}
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function KvRow({ k, v, multi }: { k: string; v: string; multi?: boolean }) {
  return (
    <div className="ir-block-card-row" style={{ alignItems: multi ? 'flex-start' : 'center' }}>
      <span className="ir-block-card-label">{k}</span>
      {multi
        ? <pre className="ir-block-card-text" style={{ maxHeight: 160 }}>{v}</pre>
        : <span className="mono" style={{ fontSize: 11 }}>{v}</span>}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function buildHeadingTree(blocks: FlatBlock[]): HeadingNode {
  const root: HeadingNode = {
    id: ROOT_ID, text: 'Document', level: 0, page: 0, blockIdx: -1,
    children: [], blocks: [], nBlocks: 0, nFigures: 0, nTables: 0,
  }
  // Stack of open headings: top = current parent.
  const stack: HeadingNode[] = [root]

  for (const b of blocks) {
    const isHeading = b.type.toLowerCase() === 'heading'
    if (isHeading) {
      // Find the closest ancestor whose level is < this heading's level.
      // Level fallback: treat unknown as 1 so we don't lose them.
      const td = b.type_data as Record<string, unknown> | null | undefined
      const level = Number((td?.level ?? (b as unknown as { level?: number }).level ?? 1))
      while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop()
      const parent = stack[stack.length - 1]
      const node: HeadingNode = {
        id: b.id, text: (b.text ?? '').trim() || `H${level}`, level, page: b.page,
        blockIdx: b.idx, children: [], blocks: [], nBlocks: 0, nFigures: 0, nTables: 0,
      }
      parent.children.push(node)
      stack.push(node)
      continue
    }
    // Non-heading blocks belong to the current section (top of stack).
    const section = stack[stack.length - 1]
    section.blocks.push(b)
    section.nBlocks++
    if (b.type.toLowerCase() === 'figure') section.nFigures++
    else if (b.type.toLowerCase() === 'table') section.nTables++
  }

  // Propagate counts upward so headings show subtree totals.
  propagateCounts(root)
  return root
}

function propagateCounts(node: HeadingNode): void {
  for (const c of node.children) {
    propagateCounts(c)
    node.nBlocks  += c.nBlocks
    node.nFigures += c.nFigures
    node.nTables  += c.nTables
  }
}

function flattenTree(node: HeadingNode, out: HeadingNode[] = []): HeadingNode[] {
  out.push(node)
  for (const c of node.children) flattenTree(c, out)
  return out
}

function blockTypeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'heading':       return '#a78bfa'
    case 'paragraph':     return '#94a3b8'
    case 'figure':        return '#6366f1'
    case 'table':         return '#34d399'
    case 'list_item':     return '#60a5fa'
    case 'caption':       return '#f59e0b'
    case 'code':          return '#f97316'
    case 'formula':       return '#ec4899'
    case 'header_footer': return '#64748b'
    default:              return '#94a3b8'
  }
}
