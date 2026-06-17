// ====== Code Summary ======
// Stage S1 block — parsed pages with full per-block detail.
// Each page shows a header row with stats; expanding reveals all IR blocks with type badge,
// id, bbox, text, and (for FIGURE blocks) the figure crop + S2 enrichment data.
// Screenshots are toggled independently with the ⊞ button.

import { useState, useEffect } from 'react'
import type { Document, PageInfo, BlockInfo } from '../../../api/types'
import { listPages, getPage, getPageScreenshotUrl, getBlockFigure } from '../../../api/client'
import { StageBlock, docStatusToStage } from './StageBlock'

interface Props {
  doc: Document
  collectionId: string
}

/**
 * Parsed document inspector — per-page block detail with figure crops and enrichment.
 */
export function S1Block({ doc, collectionId }: Props) {
  const [pages, setPages]               = useState<PageInfo[]>([])
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [expanded, setExpanded]         = useState<Set<number>>(new Set())
  const [screenshots, setScreenshots]   = useState<Set<number>>(new Set())
  const [pageBlocks, setPageBlocks]     = useState<Record<number, BlockInfo[]>>({})
  const [loadingBlocks, setLoadingBlocks] = useState<Set<number>>(new Set())
  const [figureSrcs, setFigureSrcs]     = useState<Record<string, string>>({})

  const stageStatus = docStatusToStage(doc.status)

  useEffect(() => {
    if (doc.status === 'done') void loadPages()
  }, [doc.id, doc.status])

  async function loadPages() {
    setLoading(true)
    setError(null)
    try {
      const res = await listPages(collectionId, doc.id)
      setPages(res.pages)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  async function loadPageBlocks(pageNum: number) {
    if (pageBlocks[pageNum]) return
    setLoadingBlocks(prev => { const s = new Set(prev); s.add(pageNum); return s })
    try {
      const res = await getPage(collectionId, doc.id, pageNum)
      setPageBlocks(prev => ({ ...prev, [pageNum]: res.blocks }))
      // Pre-fetch figure crop URLs for FIGURE blocks on this page
      const figures = res.blocks.filter(b => b.type.toLowerCase() === 'figure')
      await Promise.allSettled(
        figures.map(async (b) => {
          try {
            const r = await getBlockFigure(collectionId, doc.id, b.id)
            setFigureSrcs(prev => ({ ...prev, [b.id]: r.url }))
          } catch { /* crop may not exist yet (S1 skipped or S2 pending) */ }
        })
      )
    } catch { /* silently ignore page load errors */ }
    finally {
      setLoadingBlocks(prev => { const s = new Set(prev); s.delete(pageNum); return s })
    }
  }

  function toggleExpanded(pageNum: number) {
    setExpanded(prev => {
      const s = new Set(prev)
      if (s.has(pageNum)) {
        s.delete(pageNum)
      } else {
        s.add(pageNum)
        void loadPageBlocks(pageNum)
      }
      return s
    })
  }

  function toggleScreenshot(pageNum: number) {
    setScreenshots(prev => {
      const s = new Set(prev)
      if (s.has(pageNum)) { s.delete(pageNum) } else { s.add(pageNum) }
      return s
    })
  }

  const summary = doc.status === 'done'
    ? [
        doc.block_count != null ? `${doc.block_count} blocks` : null,
        doc.page_count  != null ? `${doc.page_count} pp`      : null,
        doc.language                                           ?? null,
      ].filter(Boolean).join(' · ')
    : undefined

  return (
    <StageBlock
      title="S1 — Parse"
      summary={summary}
      status={stageStatus}
      defaultOpen={doc.status === 'done'}
    >
      {doc.status !== 'done' && (
        <div className="text-muted" style={{ fontSize: 12 }}>
          {doc.status === 'running' || doc.status === 'pending'
            ? 'Parsing in progress…'
            : 'No parse results.'}
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}
      {loading && <div className="text-muted"><span className="spin">⟳</span> Loading pages…</div>}

      {pages.length > 0 && (
        <div className="page-list">
          {pages.map(page => (
            <PageRow
              key={page.page}
              page={page}
              collectionId={collectionId}
              docId={doc.id}
              isExpanded={expanded.has(page.page)}
              showScreenshot={screenshots.has(page.page)}
              blocks={pageBlocks[page.page] ?? null}
              isLoadingBlocks={loadingBlocks.has(page.page)}
              figureSrcs={figureSrcs}
              onToggleExpand={() => toggleExpanded(page.page)}
              onToggleScreenshot={() => toggleScreenshot(page.page)}
            />
          ))}
        </div>
      )}
    </StageBlock>
  )
}

// ── PageRow ───────────────────────────────────────────────────────────────────

interface PageRowProps {
  page: PageInfo
  collectionId: string
  docId: string
  isExpanded: boolean
  showScreenshot: boolean
  blocks: BlockInfo[] | null
  isLoadingBlocks: boolean
  figureSrcs: Record<string, string>
  onToggleExpand: () => void
  onToggleScreenshot: () => void
}

function PageRow({
  page, collectionId, docId, isExpanded, showScreenshot,
  blocks, isLoadingBlocks, figureSrcs, onToggleExpand, onToggleScreenshot,
}: PageRowProps) {
  return (
    <div className="page-row">
      <div className="page-row-header" onClick={onToggleExpand}>
        <span className="page-num mono">p.{page.page + 1}</span>
        <span className="page-stats">
          <span className="text-muted">{page.n_blocks} blocks</span>
          {page.n_figures > 0 && <span className="text-dim">{page.n_figures} fig</span>}
          {page.n_tables > 0  && <span className="text-dim">{page.n_tables} tbl</span>}
          {page.n_chunks > 0  && <span className="text-dim">{page.n_chunks} chunks</span>}
        </span>
        <button
          type="button"
          className="btn-icon"
          title={showScreenshot ? 'Hide screenshot' : 'Show page screenshot'}
          onClick={e => { e.stopPropagation(); onToggleScreenshot() }}
        >⊞</button>
        <span className="chunk-toggle text-dim">{isExpanded ? '▲' : '▼'}</span>
      </div>

      {showScreenshot && (
        <div className="page-screenshot-wrap fadein">
          <img
            src={getPageScreenshotUrl(collectionId, docId, page.page)}
            alt={`Page ${page.page + 1}`}
            className="page-screenshot"
            loading="lazy"
          />
        </div>
      )}

      {isExpanded && (
        <div className="block-list fadein">
          {isLoadingBlocks && (
            <div className="text-muted" style={{ padding: '8px 24px', fontSize: 12 }}>
              <span className="spin">⟳</span> Loading blocks…
            </div>
          )}
          {blocks?.map(block => (
            <BlockRow
              key={block.id}
              block={block}
              figureSrc={figureSrcs[block.id]}
            />
          ))}
          {blocks?.length === 0 && (
            <div className="text-dim" style={{ padding: '8px 24px', fontSize: 11 }}>
              No blocks on this page.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── BlockRow ──────────────────────────────────────────────────────────────────

interface BlockRowProps {
  block: BlockInfo
  figureSrc?: string
}

function BlockRow({ block, figureSrc }: BlockRowProps) {
  const [open, setOpen] = useState(false)
  const isFigure = block.type.toLowerCase() === 'figure'
  const td = block.type_data as Record<string, unknown> | null | undefined
  const color = typeColor(block.type)

  return (
    <div className="block-row">
      <div className="block-row-header" onClick={() => setOpen(o => !o)}>
        <span
          className="block-type-badge"
          style={{ background: color + '20', color, borderColor: color + '50' }}
        >
          {block.type}
        </span>
        <span className="block-id-short mono">{block.id.slice(0, 22)}…</span>
        {block.bbox.length === 4 && (
          <span className="block-bbox">
            [{block.bbox.map(v => v.toFixed(2)).join(', ')}]
          </span>
        )}
        {isFigure && td?.kind != null && (
          <span className="tag" style={{ fontSize: 10, flexShrink: 0 }}>{String(td.kind)}</span>
        )}
        <span className="block-text-preview">
          {block.text ? block.text.slice(0, 100) : isFigure ? '(figure)' : ''}
        </span>
        <span className="chunk-toggle text-dim">{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="block-detail fadein">
          {/* Full block id */}
          <div className="block-detail-row">
            <span className="block-detail-label">id</span>
            <span className="mono" style={{ fontSize: 10, wordBreak: 'break-all' }}>{block.id}</span>
          </div>

          {/* Page + bbox */}
          <div className="block-detail-row">
            <span className="block-detail-label">page (0-idx)</span>
            <span className="mono">{block.page}</span>
            <span style={{ color: 'var(--text-dim)', margin: '0 8px', fontSize: 10 }}>bbox</span>
            <span className="mono" style={{ fontSize: 10 }}>
              [{block.bbox.map(v => v.toFixed(4)).join(', ')}]
            </span>
          </div>

          {/* Text */}
          {block.text && (
            <div className="block-detail-row" style={{ alignItems: 'flex-start' }}>
              <span className="block-detail-label">text</span>
              <pre className="chunk-pre" style={{ flex: 1, margin: 0, maxHeight: 120 }}>{block.text}</pre>
            </div>
          )}

          {/* Figure enrichment (S2 data from type_data) */}
          {isFigure && td && (
            <FigureDetail td={td} figureSrc={figureSrc} blockId={block.id} />
          )}
        </div>
      )}
    </div>
  )
}

// ── FigureDetail ─────────────────────────────────────────────────────────────

interface FigureDetailProps {
  td: Record<string, unknown>
  figureSrc?: string
  blockId: string
}

function FigureDetail({ td, figureSrc, blockId }: FigureDetailProps) {
  return (
    <div className="figure-detail">
      {/* Crop image */}
      {figureSrc ? (
        <img
          src={figureSrc}
          alt={`Figure crop ${blockId}`}
          className="figure-crop-img"
          loading="lazy"
        />
      ) : (
        <span className="text-dim" style={{ fontSize: 10 }}>crop not available</span>
      )}

      {/* kind */}
      {td.kind != null && (
        <div className="block-detail-row">
          <span className="block-detail-label">kind</span>
          <span className="tag" style={{ fontSize: 10 }}>{String(td.kind)}</span>
        </div>
      )}

      {/* relevance */}
      {td.relevance != null && (
        <div className="block-detail-row">
          <span className="block-detail-label">relevance</span>
          <span className="mono">{Number(td.relevance).toFixed(3)}</span>
        </div>
      )}

      {/* crop_key */}
      {td.crop_key != null && (
        <div className="block-detail-row">
          <span className="block-detail-label">crop_key</span>
          <span className="mono text-dim" style={{ fontSize: 10, wordBreak: 'break-all' }}>{String(td.crop_key)}</span>
        </div>
      )}

      {/* ocr_text */}
      {td.ocr_text != null && (
        <div className="block-detail-row" style={{ alignItems: 'flex-start' }}>
          <span className="block-detail-label">ocr_text</span>
          <pre className="chunk-pre" style={{ flex: 1, margin: 0, maxHeight: 80, fontSize: 10 }}>
            {String(td.ocr_text)}
          </pre>
        </div>
      )}

      {/* description */}
      {td.description != null && (
        <div className="block-detail-row" style={{ alignItems: 'flex-start' }}>
          <span className="block-detail-label">description</span>
          <pre className="chunk-pre" style={{ flex: 1, margin: 0, maxHeight: 80, fontSize: 10 }}>
            {String(td.description)}
          </pre>
        </div>
      )}

      {/* data_table */}
      {td.data_table != null && Array.isArray(td.data_table) && (
        <div className="block-detail-row">
          <span className="block-detail-label">data_table</span>
          <span className="text-muted" style={{ fontSize: 11 }}>
            {(td.data_table as string[][]).length} rows ×{' '}
            {((td.data_table as string[][])[0]?.length ?? 0)} cols
          </span>
        </div>
      )}
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function typeColor(type: string): string {
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
