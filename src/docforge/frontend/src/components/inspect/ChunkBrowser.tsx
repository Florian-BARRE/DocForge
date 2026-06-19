// ====== Code Summary ======
// <ChunkBrowser> — searchable, filterable, sortable view over a document's
// chunks.  The selected chunk expands to a detailed inspector that shows the
// raw_text vs embed_text diff (where S5 prepended the heading breadcrumb is
// highlighted), the IR blocks the chunk references, and the chunk-level
// provenance dictionary.

import { useEffect, useMemo, useState } from 'react'
import type { BlockInfo, ChainTrace, ChunkResponse, Document } from '../../api/types'
import { getBlockFigure, getPage, listChunks } from '../../api/client'
import { ObjectTree } from '../ui/ObjectTree'

interface Props {
  doc: Document
  collectionId: string
}

type SortKey = 'order' | 'tokens-desc' | 'tokens-asc' | 'pages'

export function ChunkBrowser({ doc, collectionId }: Props) {
  const [chunks, setChunks] = useState<ChunkResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [strategyFilter, setStrategyFilter] = useState<string>('all')
  const [minTokens, setMinTokens] = useState<number | ''>('')
  const [maxTokens, setMaxTokens] = useState<number | ''>('')
  const [sortKey, setSortKey] = useState<SortKey>('order')
  const [openId, setOpenId] = useState<string | null>(null)

  // Per-page block cache shared across every open chunk inspector — chunks that
  // overlap a page only pay for it once.
  const [pageBlocks, setPageBlocks] = useState<Record<number, BlockInfo[]>>({})
  const [loadingPages, setLoadingPages] = useState<Set<number>>(new Set())
  const [figureSrcs, setFigureSrcs] = useState<Record<string, string>>({})

  // ── Load chunks ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (doc.status !== 'done') return
    let cancelled = false
    setLoading(true)
    setError(null)
    listChunks(collectionId, doc.id, { limit: 500 })
      .then(res => {
        if (cancelled) return
        setChunks(res.chunks)
        setTotal(res.total)
      })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [doc.id, doc.status, collectionId])

  // ── Available strategies (for the filter dropdown) ────────────────────────
  const availableStrategies = useMemo(() => {
    const s = new Set<string>()
    chunks.forEach(c => s.add(c.strategy))
    return Array.from(s).sort()
  }, [chunks])

  // ── Apply search / filters / sort ─────────────────────────────────────────
  const view = useMemo(() => {
    const q = search.trim().toLowerCase()
    const lo = typeof minTokens === 'number' ? minTokens : -Infinity
    const hi = typeof maxTokens === 'number' ? maxTokens : Infinity

    const filtered = chunks.filter(c => {
      if (strategyFilter !== 'all' && c.strategy !== strategyFilter) return false
      if (c.token_count < lo || c.token_count > hi) return false
      if (q && !(
        c.raw_text.toLowerCase().includes(q) ||
        c.embed_text.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q)
      )) return false
      return true
    })

    switch (sortKey) {
      case 'tokens-desc': filtered.sort((a, b) => b.token_count - a.token_count); break
      case 'tokens-asc':  filtered.sort((a, b) => a.token_count - b.token_count); break
      case 'pages':       filtered.sort((a, b) => firstPage(a) - firstPage(b)); break
      case 'order':       /* keep server order */ break
    }
    return filtered
  }, [chunks, search, strategyFilter, minTokens, maxTokens, sortKey])

  // ── On expansion, lazy-load pages referenced by the chunk ─────────────────
  async function ensurePages(chunk: ChunkResponse) {
    const wanted = chunkPages(chunk).filter(p => !(p in pageBlocks) && !loadingPages.has(p))
    if (wanted.length === 0) return
    setLoadingPages(prev => {
      const s = new Set(prev); wanted.forEach(p => s.add(p)); return s
    })
    await Promise.allSettled(wanted.map(async (p) => {
      try {
        const res = await getPage(collectionId, doc.id, p)
        setPageBlocks(prev => ({ ...prev, [p]: res.blocks }))
      } catch { /* swallow */ }
    }))
    setLoadingPages(prev => {
      const s = new Set(prev); wanted.forEach(p => s.delete(p)); return s
    })
  }

  function toggleOpen(chunk: ChunkResponse) {
    const willOpen = openId !== chunk.id
    setOpenId(willOpen ? chunk.id : null)
    if (willOpen) {
      void ensurePages(chunk)
      // Figure chunks: pre-fetch the figure crop URL.
      if (chunk.strategy === 'figure' && chunk.block_ids[0] && figureSrcs[chunk.id] === undefined) {
        getBlockFigure(collectionId, doc.id, chunk.block_ids[0])
          .then(r => setFigureSrcs(prev => ({ ...prev, [chunk.id]: r.url })))
          .catch(() => setFigureSrcs(prev => ({ ...prev, [chunk.id]: '' })))
      }
    }
  }

  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12, padding: 12 }}>
        {doc.status === 'running' || doc.status === 'pending'
          ? 'Chunking in progress…'
          : 'No chunks available.'}
      </div>
    )
  }
  if (loading) return <div className="text-muted" style={{ padding: 12 }}><span className="spin">⟳</span> Loading chunks…</div>
  if (error) return <div className="error-banner">{error}</div>

  return (
    <div className="chunk-browser">
      {/* ── Toolbar ── */}
      <div className="chunk-browser-toolbar">
        <input
          className="input"
          type="text"
          placeholder="Search raw / embed text or chunk id…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: 200, fontSize: 12 }}
        />
        <select
          className="input select"
          value={strategyFilter}
          onChange={e => setStrategyFilter(e.target.value)}
          style={{ width: 130, fontSize: 12 }}
        >
          <option value="all">All strategies</option>
          {availableStrategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          className="input"
          type="number"
          placeholder="min tok"
          value={minTokens}
          onChange={e => setMinTokens(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          style={{ width: 80, fontSize: 12 }}
        />
        <input
          className="input"
          type="number"
          placeholder="max tok"
          value={maxTokens}
          onChange={e => setMaxTokens(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          style={{ width: 80, fontSize: 12 }}
        />
        <select
          className="input select"
          value={sortKey}
          onChange={e => setSortKey(e.target.value as SortKey)}
          style={{ width: 150, fontSize: 12 }}
        >
          <option value="order">Reading order</option>
          <option value="tokens-desc">Tokens ↓</option>
          <option value="tokens-asc">Tokens ↑</option>
          <option value="pages">First page</option>
        </select>
        <span className="text-dim" style={{ fontSize: 11 }}>
          {view.length}/{total}
        </span>
      </div>

      {/* ── List ── */}
      <div className="chunk-browser-list">
        {view.length === 0 && (
          <div className="text-dim" style={{ fontSize: 11, padding: 12 }}>
            No chunks match the current filter.
          </div>
        )}
        {view.map((chunk, idx) => {
          const isOpen = openId === chunk.id
          return (
            <ChunkCard
              key={chunk.id}
              rank={idx + 1}
              chunk={chunk}
              isOpen={isOpen}
              onToggle={() => toggleOpen(chunk)}
              pageBlocks={pageBlocks}
              loadingPages={loadingPages}
              figureSrc={figureSrcs[chunk.id]}
            />
          )
        })}
      </div>
    </div>
  )
}

// ── ChunkCard ────────────────────────────────────────────────────────────────

function ChunkCard({
  rank, chunk, isOpen, onToggle, pageBlocks, loadingPages, figureSrc,
}: {
  rank: number
  chunk: ChunkResponse
  isOpen: boolean
  onToggle: () => void
  pageBlocks: Record<number, BlockInfo[]>
  loadingPages: Set<number>
  figureSrc: string | undefined
}) {
  const pages = chunkPages(chunk)
  const heading = chunkHeadingPath(chunk)
  const [tab, setTab] = useState<'embed' | 'diff' | 'blocks' | 'prov'>('embed')

  // Compute the header that S5 added: embed_text - raw_text suffix.
  const { headerPart, bodyPart } = useMemo(() => splitEmbedHeader(chunk), [chunk])

  return (
    <div className={`chunk-browser-card ${isOpen ? 'chunk-browser-card-open' : ''}`}>
      <div className="chunk-browser-card-header" onClick={onToggle}>
        <span className="chunk-browser-rank mono text-dim">#{rank}</span>
        <span className="tag" style={{ fontSize: 10 }}>{chunk.strategy}</span>
        {pages.length > 0 && (
          <span className="mono text-dim" style={{ fontSize: 10 }}>p.{pages.join(',')}</span>
        )}
        <span className="mono text-dim" style={{ fontSize: 10 }}>{chunk.token_count} tok</span>
        {chunk.parent_id && (
          <span className="tag" style={{ fontSize: 9 }}>child</span>
        )}
        <span className="chunk-browser-preview text-muted">
          {chunk.raw_text.slice(0, 140)}
        </span>
        <span className="text-dim" style={{ fontSize: 10 }}>{isOpen ? '▲' : '▼'}</span>
      </div>

      {isOpen && (
        <div className="chunk-browser-card-body fadein">
          {heading && (
            <div className="chunk-browser-breadcrumb mono text-muted">
              ↳ {heading}
            </div>
          )}

          {chunk.strategy === 'figure' && (
            <div style={{ margin: '6px 0' }}>
              {figureSrc
                ? <img src={figureSrc} alt={`chunk ${chunk.id}`} loading="lazy" style={{ maxWidth: 280, maxHeight: 280, border: '1px solid var(--border)', borderRadius: 4 }} />
                : figureSrc === '' ? <span className="text-dim" style={{ fontSize: 10 }}>crop not available</span>
                : <span className="text-dim" style={{ fontSize: 10 }}><span className="spin">⟳</span> loading crop…</span>
              }
            </div>
          )}

          {/* ── Tabs ── */}
          <div className="chunk-browser-tabs">
            <TabBtn label="Embed text"  active={tab === 'embed'}  onClick={() => setTab('embed')} />
            <TabBtn label="Diff vs raw" active={tab === 'diff'}   onClick={() => setTab('diff')} />
            <TabBtn label={`Blocks · ${chunk.block_ids.length}`}  active={tab === 'blocks'} onClick={() => setTab('blocks')} />
            <TabBtn label="Provenance" active={tab === 'prov'}   onClick={() => setTab('prov')} />
          </div>

          {/* ── Tab contents ── */}
          {tab === 'embed' && (
            <pre className="chunk-browser-pre">{chunk.embed_text}</pre>
          )}

          {tab === 'diff' && (
            <div>
              <div className="text-dim" style={{ fontSize: 10, marginBottom: 4 }}>
                Highlight: <span style={{ color: 'var(--accent)' }}>S5 header</span> +
                <span style={{ color: 'var(--text)' }}> chunk body</span>
              </div>
              <pre className="chunk-browser-pre">
                {headerPart && (
                  <span style={{ background: 'var(--accent-soft)', color: 'var(--accent)', padding: '0 2px', borderRadius: 2 }}>
                    {headerPart}
                  </span>
                )}
                {bodyPart}
              </pre>
              {!headerPart && (
                <div className="text-dim" style={{ fontSize: 10, marginTop: 4 }}>
                  No header was prepended (S5 contextualize disabled or breadcrumb absent).
                </div>
              )}
            </div>
          )}

          {tab === 'blocks' && (
            <ChunkBlocks
              chunk={chunk}
              pageBlocks={pageBlocks}
              loadingPages={loadingPages}
            />
          )}

          {tab === 'prov' && (
            <ObjectTree value={chunk.prov} label="prov" defaultDepth={1} />
          )}
        </div>
      )}
    </div>
  )
}

function TabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={`chunk-browser-tab ${active ? 'chunk-browser-tab-active' : ''}`}
      onClick={onClick}
    >{label}</button>
  )
}

// ── ChunkBlocks — IR blocks the chunk references ───────────────────────────

function ChunkBlocks({
  chunk, pageBlocks, loadingPages,
}: {
  chunk: ChunkResponse
  pageBlocks: Record<number, BlockInfo[]>
  loadingPages: Set<number>
}) {
  const pages = chunkPages(chunk)
  const wanted = new Set(chunk.block_ids)
  const allLoaded = pages.every(p => p in pageBlocks)
  const anyLoading = pages.some(p => loadingPages.has(p))

  const byId: Record<string, BlockInfo> = {}
  pages.forEach(p => (pageBlocks[p] ?? []).forEach(b => { if (wanted.has(b.id)) byId[b.id] = b }))
  const ordered = chunk.block_ids.map(id => byId[id]).filter(Boolean) as BlockInfo[]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {anyLoading && !allLoaded && (
        <span className="text-dim" style={{ fontSize: 10 }}><span className="spin">⟳</span> loading blocks…</span>
      )}
      {ordered.length === 0 && !anyLoading && (
        <span className="text-dim" style={{ fontSize: 10 }}>blocks not loaded.</span>
      )}
      {ordered.map(b => <BlockEnrichmentCard key={b.id} block={b} />)}
    </div>
  )
}

// ── BlockEnrichmentCard — labelled view of one IR block ─────────────────────
// Shows EXPLICITLY which enrichment field came from which sub-stage:
//   • text         (paragraph / caption / heading text from S1)
//   • table        (S1 table extraction)
//   • figure.ocr_text       (S2 OCR chain output)
//   • figure.description    (S2 VLM chain output)
//   • figure.data_table     (S2 VLM chart-to-data output)
//   • figure.kind / relevance (S2 classifier output)
// And the chain_traces that produced each.  Missing fields are shown as such
// so the user sees "VLM was empty" instead of "the chunk has no description".

function BlockEnrichmentCard({ block }: { block: BlockInfo }) {
  const colour = blockTypeColor(block.type)
  const td = (block.type_data ?? {}) as Record<string, unknown>
  const isFigure = block.type.toLowerCase() === 'figure'
  const isTable = block.type.toLowerCase() === 'table'

  return (
    <div className="enrich-card">
      <div className="enrich-card-head">
        <span className="tag" style={{
          color: colour, borderColor: colour + '40', background: colour + '15',
          fontSize: 9, padding: '1px 5px',
        }}>{block.type}</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>p.{block.page + 1}</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>{block.id.slice(0, 18)}…</span>
        {isFigure && td.kind != null && (
          <span className="tag" style={{ fontSize: 9, padding: '1px 5px' }}>kind: {String(td.kind)}</span>
        )}
        {isFigure && td.relevance != null && (
          <span className="mono text-dim" style={{ fontSize: 10 }}>relevance {Number(td.relevance).toFixed(2)}</span>
        )}
      </div>

      {/* Paragraph / caption / heading text */}
      {block.text ? (
        <EnrichField label="text" source="parser" value={block.text} />
      ) : null}

      {/* Table */}
      {isTable && Array.isArray(td.cells) && (td.cells as string[][]).length > 0 ? (
        <EnrichField
          label="table"
          source="parser"
          value={(td.cells as string[][]).slice(0, 3)
            .map(row => row.join(' | '))
            .join('\n') + (((td.cells as string[][]).length > 3) ? `\n… (${(td.cells as string[][]).length - 3} more rows)` : '')}
        />
      ) : null}

      {/* Figure enrichment — one field per sub-stage, with routing-aware reason
          when the field is empty.  S2's routing matrix:
            DECORATIVE   → no OCR, no VLM           (skip total)
            SCANNED_TEXT → OCR yes, VLM no          (text image → OCR is enough)
            CHART        → OCR yes, VLM yes + table (rich enrichment)
            DIAGRAM      → OCR yes, VLM yes
            PHOTO        → OCR no,  VLM yes         (no text to extract)
       */}
      {isFigure ? (
        <>
          <EnrichField
            label="ocr_text"
            source="S2 · OCR"
            value={td.ocr_text as string | undefined}
            emptyReason={emptyReasonForOCR(td.kind, block.chain_traces ?? [])}
            optional
          />
          <EnrichField
            label="description"
            source="S2 · VLM"
            value={td.description as string | undefined}
            emptyReason={emptyReasonForVLM(td.kind, block.chain_traces ?? [])}
            optional
          />
          {Array.isArray(td.data_table) && (td.data_table as string[][]).length > 0 ? (
            <EnrichField
              label="data_table"
              source="S2 · chart-to-data"
              value={(td.data_table as string[][]).slice(0, 4)
                .map(row => row.join('\t'))
                .join('\n') + (((td.data_table as string[][]).length > 4) ? `\n… (${(td.data_table as string[][]).length - 4} more rows)` : '')}
            />
          ) : isFigure && td.kind === 'chart' ? (
            <EnrichField
              label="data_table"
              source="S2 · chart-to-data"
              value={undefined}
              emptyReason="chart_to_data not enabled on the pipeline (enrich.chart_to_data=false)"
              optional
            />
          ) : null}
        </>
      ) : null}

      {/* Chain traces — make the provenance of each sub-stage explicit */}
      {block.chain_traces && block.chain_traces.length > 0 ? (
        <div className="enrich-traces">
          {block.chain_traces.map((t, i) => {
            const n = t.attempts?.length ?? 0
            const colour =
              t.stage === 'classifier' ? '#a855f7' :
              t.stage === 'ocr'        ? '#f59e0b' :
              t.stage === 'vlm'        ? '#ec4899' :
              '#94a3b8'
            const exhausted = t.final_provider == null
            return (
              <span key={i} className="enrich-trace-pill" style={{
                background: colour + '20',
                color: colour,
                borderColor: colour + '40',
              }}>
                {t.stage} · {t.final_provider ?? 'exhausted'} · {n} att.
                {exhausted && ' ⚠'}
              </span>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function EnrichField({
  label, source, value, optional, emptyReason,
}: {
  label: string
  source: string
  value: string | undefined
  optional?: boolean
  // Routing- or chain-aware explanation shown when the field is empty.
  // Examples: "routing skip (kind=SCANNED_TEXT)", "chain exhausted",
  // "no provider configured", "chart_to_data disabled".  Falls back to a
  // generic message when not provided.
  emptyReason?: string
}) {
  const hasValue = !!value && value.trim().length > 0
  if (!hasValue && !optional) return null
  return (
    <div className="enrich-field">
      <div className="enrich-field-head">
        <span className="mono enrich-field-label">{label}</span>
        <span className="enrich-field-source">{source}</span>
        {!hasValue && (
          <span className="enrich-field-empty">
            — {emptyReason ?? "empty (provider didn't run or produced no output)"}
          </span>
        )}
      </div>
      {hasValue && (
        <pre className="enrich-field-value">{value}</pre>
      )}
    </div>
  )
}

// ── Routing-aware empty-reason helpers ─────────────────────────────────────

/** S2's _OCR_KINDS = {SCANNED_TEXT, CHART, DIAGRAM}.  Anything else skips OCR. */
const OCR_KINDS = new Set(['scanned_text', 'chart', 'diagram'])
/** S2's _VLM_KINDS = {CHART, DIAGRAM, PHOTO}.  Anything else skips VLM. */
const VLM_KINDS = new Set(['chart', 'diagram', 'photo'])

function emptyReasonForOCR(kind: unknown, traces: ChainTrace[]): string {
  const k = String(kind ?? '').toLowerCase()
  if (k && !OCR_KINDS.has(k)) {
    return `routing skip — kind '${k}' is not in OCR_KINDS = {SCANNED_TEXT, CHART, DIAGRAM}`
  }
  const ocr = traces.find(t => t.stage === 'ocr')
  if (!ocr) return 'OCR chain not invoked (no provider configured or no figure crop available)'
  if (ocr.final_provider == null) {
    const n = ocr.attempts?.length ?? 0
    return `OCR chain exhausted after ${n} attempt${n !== 1 ? 's' : ''} — every provider escalated or raised`
  }
  return 'OCR ran but produced empty text'
}

function emptyReasonForVLM(kind: unknown, traces: ChainTrace[]): string {
  const k = String(kind ?? '').toLowerCase()
  if (k && !VLM_KINDS.has(k)) {
    return `routing skip — kind '${k}' is not in VLM_KINDS = {CHART, DIAGRAM, PHOTO}`
  }
  const vlm = traces.find(t => t.stage === 'vlm')
  if (!vlm) return 'VLM chain not invoked (no provider configured or budget exhausted before this figure)'
  if (vlm.final_provider == null) {
    const n = vlm.attempts?.length ?? 0
    return `VLM chain exhausted after ${n} attempt${n !== 1 ? 's' : ''} — every provider escalated or raised`
  }
  return 'VLM ran but produced an empty description'
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function chunkPages(c: ChunkResponse): number[] {
  const prov = c.prov as Record<string, unknown> | undefined
  const pages = prov?.pages
  return Array.isArray(pages) ? (pages as number[]) : []
}

function firstPage(c: ChunkResponse): number {
  const p = chunkPages(c)
  return p.length > 0 ? p[0] : Infinity
}

function chunkHeadingPath(c: ChunkResponse): string | null {
  const prov = c.prov as Record<string, unknown> | undefined
  const hp = prov?.heading_path
  return typeof hp === 'string' ? hp : null
}

function splitEmbedHeader(c: ChunkResponse): { headerPart: string; bodyPart: string } {
  const idx = c.embed_text.lastIndexOf(c.raw_text)
  if (idx <= 0) return { headerPart: '', bodyPart: c.embed_text }
  return {
    headerPart: c.embed_text.slice(0, idx),
    bodyPart: c.embed_text.slice(idx),
  }
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
