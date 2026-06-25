// ====== Code Summary ======
// PagesTab — thumbnail grid of document pages.  Clicking a thumbnail lazily
// loads the full page detail (large screenshot + IR block list).

// ====== Standard Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getPage, getPageScreenshotUrl, listPages } from '../../../api/client'
import type { Document, PageDetailResponse, PageInfo } from '../../../api/types'

// ====== Local Project Imports ======
import { FigureCropImage } from './FigureCropImage'

interface PagesTabProps {
  collectionId: string
  docId: string
  doc: Document
}

/**
 * Renders a thumbnail grid of document pages. Clicking a thumbnail loads
 * the full page detail (screenshot + block list).
 *
 * Args:
 *   collectionId: Collection identifier for API calls.
 *   docId:        Document identifier for API calls.
 *   doc:          Document record (used for status guard).
 */
export function PagesTab({ collectionId, docId, doc }: PagesTabProps) {
  const [pages, setPages]             = useState<PageInfo[]>([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [selectedPage, setSelectedPage] = useState<number | null>(null)
  const [pageDetail, setPageDetail]   = useState<PageDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // 1. Fetch page list when the document is done.
  useEffect(() => {
    if (doc.status !== 'done') return
    setLoading(true)
    listPages(collectionId, docId)
      .then(res => setPages(res.pages))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))
  }, [collectionId, docId, doc.status])

  // 2. Fetch page detail when a page is selected.
  useEffect(() => {
    if (selectedPage == null) { setPageDetail(null); return }
    setDetailLoading(true)
    getPage(collectionId, docId, selectedPage)
      .then(setPageDetail)
      .catch(() => setPageDetail(null))
      .finally(() => setDetailLoading(false))
  }, [collectionId, docId, selectedPage])

  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12 }}>
        {doc.status === 'running' || doc.status === 'pending'
          ? 'Processing in progress…'
          : 'No pages available.'}
      </div>
    )
  }

  if (loading) {
    return <div className="text-muted"><span className="spin">⟳</span> Loading pages…</div>
  }

  if (error) {
    return <div className="error-banner">{error}</div>
  }

  return (
    <div>
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
        <div className="fadein" style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          background: 'var(--surface-raised)',
          padding: 12,
          marginTop: 8,
        }}>
          {/* Large screenshot */}
          <div style={{ marginBottom: 12 }}>
            <img
              src={getPageScreenshotUrl(collectionId, docId, selectedPage)}
              alt={`Page ${selectedPage + 1}`}
              style={{ maxWidth: '100%', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', display: 'block' }}
            />
          </div>

          {/* Block list */}
          {detailLoading ? (
            <div className="text-muted" style={{ fontSize: 12 }}>
              <span className="spin">⟳</span> Loading blocks…
            </div>
          ) : pageDetail ? (
            <div>
              <div className="stage-panel-label" style={{ marginBottom: 8 }}>
                {pageDetail.blocks.length} blocks on page {selectedPage + 1}
              </div>
              {pageDetail.blocks.map(block => (
                <div key={block.id} className="block-row" style={{ borderBottom: '1px solid var(--border)', padding: '5px 0', fontSize: 11, display: 'flex', flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="block-type-badge" style={{ marginRight: 8 }}>{block.type}</span>
                  <span className="mono text-dim" style={{ fontSize: 10 }}>{block.id.slice(0, 22)}…</span>
                  {block.text && (
                    <span className="text-muted" style={{ marginLeft: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                      {block.text.slice(0, 120)}
                    </span>
                  )}
                  {/* Figure blocks: render the actual extracted crop image, not just the text row. */}
                  {block.type.toLowerCase() === 'figure' && (
                    <div style={{ flexBasis: '100%', marginTop: 6 }}>
                      <FigureCropImage collectionId={collectionId} docId={docId} blockId={block.id} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}
