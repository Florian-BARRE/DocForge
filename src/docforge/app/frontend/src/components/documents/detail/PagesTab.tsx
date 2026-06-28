// ====== Code Summary ======
// PagesTab — thumbnail grid of document pages.  Clicking a thumbnail lazily
// loads the full page detail: screenshot with block bbox overlays + block list.
// activeBlockId is lifted here so PageBlockOverlay and PageBlockList can
// cross-highlight the same block.

// ====== Standard Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getPage, getPageScreenshotUrl, listPages } from '../../../api/client'
import type { Document, PageDetailResponse, PageInfo } from '../../../api/types'
import { EmptyState } from '../../ui/primitives/EmptyState'
import { Spinner } from '../../ui/primitives/Spinner'

// ====== Local Project Imports ======
import { PageBlockList } from './PageBlockList'
import { PageBlockOverlay } from './PageBlockOverlay'

interface PagesTabProps {
  collectionId: string
  docId: string
  doc: Document
}

/**
 * Renders a thumbnail grid of document pages.  Clicking a thumbnail loads
 * the full page detail: screenshot with block bbox overlays and a block list.
 *
 * activeBlockId is lifted here so PageBlockOverlay and PageBlockList
 * can cross-highlight each other without parent drilling.
 *
 * Args:
 *   collectionId: Collection identifier for API calls.
 *   docId:        Document identifier for API calls.
 *   doc:          Document record (used for status guard).
 */
export function PagesTab({ collectionId, docId, doc }: PagesTabProps) {
  const [pages, setPages]           = useState<PageInfo[]>([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [selectedPage, setSelectedPage] = useState<number | null>(null)
  const [pageDetail, setPageDetail] = useState<PageDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  // Shared highlight: drives cross-highlight between overlay boxes and list rows.
  const [activeBlockId, setActiveBlockId] = useState<string | null>(null)

  // 1. Fetch page list when the document is done.
  useEffect(() => {
    if (doc.status !== 'done') return
    setLoading(true)
    listPages(collectionId, docId)
      .then(res => setPages(res.pages))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))
  }, [collectionId, docId, doc.status])

  // 2. Fetch page detail when a page is selected; reset active block.
  useEffect(() => {
    if (selectedPage == null) { setPageDetail(null); setActiveBlockId(null); return }
    setDetailLoading(true)
    setActiveBlockId(null)
    getPage(collectionId, docId, selectedPage)
      .then(setPageDetail)
      .catch(() => setPageDetail(null))
      .finally(() => setDetailLoading(false))
  }, [collectionId, docId, selectedPage])

  if (doc.status !== 'done') {
    if (doc.status === 'running' || doc.status === 'pending') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Spinner size={14} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Processing in progress…</span>
        </div>
      )
    }
    return <EmptyState message="No pages available." />
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Spinner size={14} />
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading pages…</span>
      </div>
    )
  }

  if (error) {
    return <div className="error-banner">{error}</div>
  }

  return (
    <div>
      {/* Empty state — document processed but has no pages (non-page formats) */}
      {pages.length === 0 && (
        <EmptyState message="No pages available." description="This document has no page-level data." />
      )}

      {/* Thumbnail grid */}
      <div className="pages-grid" style={{ marginBottom: selectedPage != null ? 16 : 0 }}>
        {pages.map(page => (
          <div
            key={page.page}
            className={`page-thumb ${selectedPage === page.page ? 'page-thumb-selected' : ''}`}
            onClick={() => setSelectedPage(selectedPage === page.page ? null : page.page)}
            title={`Page ${page.page + 1} — ${page.n_blocks} blocks`}
          >
            <img
              src={getPageScreenshotUrl(collectionId, docId, page.page)}
              alt={`Page ${page.page + 1}`}
              loading="lazy"
            />
            <div style={{ padding: '3px 6px', fontSize: 10, color: 'var(--text-dim)', textAlign: 'center' }}>
              p.{page.page + 1}
            </div>
          </div>
        ))}
      </div>

      {/* Expanded page detail */}
      {selectedPage != null && (
        <div
          className="fadein"
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            background: 'var(--surface-raised)',
            padding: 12,
            marginTop: 8,
          }}
        >
          {detailLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Spinner size={14} />
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading page detail…</span>
            </div>
          ) : pageDetail ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Page header */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span className="section-title" style={{ margin: 0 }}>
                  Page {selectedPage + 1}
                </span>
                <span className="tag" style={{ fontSize: 10 }}>
                  {pageDetail.blocks.length} blocks
                </span>
                <span className="text-dim" style={{ fontSize: 10 }}>
                  Click a block box or a list row to inspect it
                </span>
              </div>

              {/* Screenshot + bbox overlays (cross-highlighted with the list) */}
              <PageBlockOverlay
                blocks={pageDetail.blocks}
                screenshotUrl={getPageScreenshotUrl(collectionId, docId, selectedPage)}
                activeId={activeBlockId}
                onBlockActivate={setActiveBlockId}
              />

              {/* Block detail list (cross-highlighted with the overlay) */}
              <PageBlockList
                blocks={pageDetail.blocks}
                activeId={activeBlockId}
                onBlockActivate={setActiveBlockId}
              />
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
