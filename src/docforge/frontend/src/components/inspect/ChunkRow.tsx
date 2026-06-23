// ====== Code Summary ======
// ChunkRow — the collapsed/expanded card for a single chunk in ChunkBrowser.
// Expanding reveals the embed/raw diff, the referenced IR blocks (with per
// sub-stage enrichment provenance), and the chunk-level provenance tree.
// Includes the locally-scoped block/enrichment views and routing-aware
// empty-reason helpers.

// ====== Standard Library Imports ======
import { useMemo, useState } from 'react'

// ====== Internal Project Imports ======
import type { BlockInfo, ChainTrace, ChunkResponse } from '../../api/types'
import { ObjectTree } from '../ui/ObjectTree'

// ====== Local Project Imports ======
import { blockTypeColor, chunkHeadingPath, chunkPages, splitEmbedHeader } from './chunkHelpers'

/**
 * Collapsed/expanded inspector card for a single chunk.
 *
 * Args:
 *   rank:         1-based display rank within the current view.
 *   chunk:        The chunk record to render.
 *   isOpen:       Whether the card is expanded.
 *   onToggle:     Callback to toggle the expanded state.
 *   pageBlocks:   Shared per-page block cache.
 *   loadingPages: Set of page indices currently being fetched.
 *   figureSrc:    Pre-fetched figure crop URL ('' when unavailable, undefined while loading).
 */
export function ChunkCard({
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
