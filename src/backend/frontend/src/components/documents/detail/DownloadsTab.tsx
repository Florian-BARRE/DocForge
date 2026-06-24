// ====== Code Summary ======
// DownloadsTab — presigned-URL download buttons for the document's original
// file, generated markdown, and generated PDF.  DownloadButton is the
// locally-scoped action button that fetches a URL on click and opens it.

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import {
  getDocumentMarkdown,
  getDocumentOriginal,
  getDocumentPdf,
} from '../../../api/client'
import type { Document, PresignedUrlResponse } from '../../../api/types'

interface DownloadsTabProps {
  collectionId: string
  docId: string
  doc: Document
}

interface DownloadButtonProps {
  label: string
  icon: string
  available: boolean
  fetchUrl: () => Promise<PresignedUrlResponse>
}

/**
 * A download action button that fetches a presigned URL on click, then opens
 * it in a new tab. Shows a loading spinner during fetch and an error on failure.
 *
 * Args:
 *   label:    Human-readable label for the button.
 *   icon:     Emoji or text icon shown to the left of the label.
 *   available: Whether the file exists (guards against API errors for missing files).
 *   fetchUrl: Async function that resolves a PresignedUrlResponse.
 */
function DownloadButton({ label, icon, available, fetchUrl }: DownloadButtonProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  /**
   * Fetches the presigned URL and opens it in a new tab.
   */
  async function handleClick() {
    // 1. Guard: nothing to download if unavailable.
    if (!available || loading) return

    // 2. Fetch the URL and open it.
    setLoading(true)
    setError(null)
    try {
      const { url } = await fetchUrl()
      window.open(url, '_blank')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button
        type="button"
        className="doc-download-btn"
        disabled={!available || loading}
        onClick={handleClick}
      >
        <span style={{ fontSize: 18 }}>{icon}</span>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{label}</span>
          {!available && (
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              Not available yet — process the document first
            </span>
          )}
        </div>
        {loading && <span className="spin" style={{ marginLeft: 'auto', color: 'var(--text-dim)' }}>⟳</span>}
        {!loading && available && (
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 12 }}>↓</span>
        )}
      </button>
      {error && (
        <div className="error-banner" style={{ marginTop: 4, fontSize: 11 }}>{error}</div>
      )}
    </div>
  )
}

/**
 * Renders the Downloads tab with three presigned-URL download buttons for the
 * document's original file, generated markdown, and generated PDF.
 *
 * Args:
 *   collectionId: Collection identifier forwarded to API calls.
 *   docId:        Document identifier forwarded to API calls.
 *   doc:          Document record — used to check availability flags.
 */
export function DownloadsTab({ collectionId, docId, doc }: DownloadsTabProps) {
  return (
    <div className="doc-detail-downloads">
      <DownloadButton
        label="Original file"
        icon="📄"
        available={doc.has_original}
        fetchUrl={() => getDocumentOriginal(collectionId, docId)}
      />
      <DownloadButton
        label="Markdown"
        icon="📝"
        available={doc.has_markdown}
        fetchUrl={() => getDocumentMarkdown(collectionId, docId)}
      />
      <DownloadButton
        label="PDF"
        icon="🗒️"
        available={doc.has_pdf}
        fetchUrl={() => getDocumentPdf(collectionId, docId)}
      />
    </div>
  )
}
