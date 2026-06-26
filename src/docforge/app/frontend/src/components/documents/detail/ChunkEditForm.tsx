// ====== Code Summary ======
// ChunkEditForm — inline edit form for a single chunk in the Chunks browser.
// Exposes raw_text and embed_text as editable textareas plus a "re-embed"
// toggle.  Save calls updateChunk; the backend warning (async reindex note)
// and any HTTP errors are surfaced inline, not console-only.
// Rendered only when canWrite is true (caller's responsibility).

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { HttpError, updateChunk } from '../../../api/client'
import type { ChunkResponse, ChunkUpdateResponse } from '../../../api/types'

interface ChunkEditFormProps {
  /** Chunk to edit. */
  chunk: ChunkResponse
  /** Collection this chunk belongs to. */
  collectionId: string
  /** Called with the API response after a successful save. */
  onSaved: (updated: ChunkUpdateResponse) => void
  /** Called when the user cancels editing. */
  onCancel: () => void
}

/**
 * Inline chunk editor.
 *
 * Renders raw_text and embed_text as textareas initialized from the chunk.
 * The "Re-embed" toggle requests vector reindexing alongside the text update.
 * Warnings from the backend (e.g. async reindex note) are shown in an info
 * banner.  HTTP errors appear as error banners — no silent console drops.
 *
 * Args:
 *   chunk:        Chunk to edit.
 *   collectionId: UUID of the owning collection.
 *   onSaved:      Called with the backend response after a successful save.
 *   onCancel:     Called when the user dismisses the form without saving.
 */
export function ChunkEditForm({ chunk, collectionId, onSaved, onCancel }: ChunkEditFormProps) {
  const [rawText, setRawText]     = useState(chunk.raw_text)
  const [embedText, setEmbedText] = useState(chunk.embed_text)
  const [reindex, setReindex]     = useState(false)
  const [saving, setSaving]       = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [warning, setWarning]     = useState<string | null>(null)
  // Holds the saved response while a warning is displayed — the form stays mounted so the
  // backend warning is actually seen; "Done" then propagates this result to the parent.
  const [savedRes, setSavedRes]   = useState<ChunkUpdateResponse | null>(null)

  // 1. Determine whether any change has been made.
  const rawChanged   = rawText   !== chunk.raw_text
  const embedChanged = embedText !== chunk.embed_text
  const isDirty = rawChanged || embedChanged || reindex

  // 2. Persist changes via the chunk update endpoint.
  async function save() {
    setSaving(true)
    setError(null)
    setWarning(null)
    try {
      const res = await updateChunk(collectionId, chunk.document_id, chunk.id, {
        raw_text:   rawChanged   ? rawText   : undefined,
        embed_text: embedChanged ? embedText : undefined,
        reindex,
      })
      // Backend may attach a warning (e.g. reindex is async). When present, keep the form
      // mounted so the warning is visible — otherwise onSaved() switches tab and unmounts us
      // before it can render. The user dismisses it via "Done", which then propagates the result.
      if (res.warning) {
        setWarning(res.warning)
        setSavedRes(res)
      } else {
        onSaved(res)
      }
    } catch (err) {
      setError(
        err instanceof HttpError
          ? `Save failed (HTTP ${err.status}): ${err.message}`
          : String(err),
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="chunk-edit-form">
      {/* raw_text textarea */}
      <div className="chunk-edit-field">
        <div className="chunk-edit-label">
          raw_text <span className="text-dim">(displayed / cited text)</span>
        </div>
        <textarea
          className="input chunk-edit-textarea"
          value={rawText}
          onChange={e => setRawText(e.target.value)}
          rows={6}
          spellCheck={false}
        />
      </div>

      {/* embed_text textarea */}
      <div className="chunk-edit-field">
        <div className="chunk-edit-label">
          embed_text <span className="text-dim">(sent to the embedding model, may include S5 header)</span>
        </div>
        <textarea
          className="input chunk-edit-textarea"
          value={embedText}
          onChange={e => setEmbedText(e.target.value)}
          rows={6}
          spellCheck={false}
        />
      </div>

      {/* Re-embed toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          type="button"
          className={`toggle ${reindex ? 'toggle-on' : ''}`}
          onClick={() => setReindex(r => !r)}
          aria-pressed={reindex}
          title="Re-embed and re-index this chunk's vectors after saving"
        >
          <span className="toggle-thumb" />
        </button>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Re-embed after save
          {reindex && <span className="text-dim" style={{ marginLeft: 6, fontSize: 11 }}>(rewrites vectors in Qdrant)</span>}
        </span>
      </div>

      {/* Warning from backend (e.g. reindex queued asynchronously) */}
      {warning && (
        <div className="info-banner">
          <span className="info-icon">i</span>
          {warning}
        </div>
      )}

      {/* Error banner */}
      {error && <div className="error-banner">{error}</div>}

      {/* Actions — once a warning is shown the save is committed, so only "Done" remains
          (it propagates the saved result to the parent, which closes the editor). */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        {savedRes ? (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onSaved(savedRes)}
          >
            Done
          </button>
        ) : (
          <>
            <button
              type="button"
              className="btn"
              onClick={onCancel}
              disabled={saving}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void save()}
              disabled={saving || !isDirty}
            >
              {saving ? <span className="spin">⟳</span> : 'Save'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
