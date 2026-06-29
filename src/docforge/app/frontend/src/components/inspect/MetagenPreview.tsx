// ====== Code Summary ======
// <MetagenPreview> — dry-run preview for S5b LLM-generated metadata fields.
//
// Lets the user validate a prompt before paying for a full ingestion:
//   1. Pick a generated field (from the collection's generated metadata fields).
//   2. Enter sample text (always available) or, when a document is provided,
//      pick a stored chunk instead.
//   3. Call POST /collections/{id}/metagen/preview.
//   4. Show the generated value, token/cost estimates, provider ID, degraded badge.
//
// Modeled on ContextualizePreview: same chunk-picker UX pattern, but calls the
// live LLM chain rather than computing locally.
//
// A clear "preview unavailable" empty state is shown on HTTP 422 (no provider or
// no target configured for the requested field).

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import type { ChunkResponse, Document, MetaField, MetagenPreviewResponse } from '../../api/types'
import { HttpError, listChunks, previewMetagen } from '../../api/client'

// ── Types ─────────────────────────────────────────────────────────────────────

interface MetagenPreviewProps {
  /** Target collection. */
  collectionId: string
  /**
   * Generated metadata fields available for preview (origin === 'generated').
   * When empty the component renders an informational empty state.
   */
  generatedFields: MetaField[]
  /**
   * Optional document for chunk-picking mode.  When absent the component shows a
   * sample-text textarea instead (no API calls are needed to load chunks).
   */
  doc?: Document | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Dry-run preview panel for S5b metagen fields.
 *
 * Two input modes:
 *   - Sample-text (default / when doc is absent): user enters raw chunk text directly.
 *   - Chunk-picker (when doc is provided + document is done): select a stored chunk.
 *
 * The preview call requires CONFIG_WRITE.  On a 422 (no LLM chain or no matching
 * target) the UI shows a calm "preview unavailable" note instead of an error toast.
 *
 * Args:
 *   collectionId:    Target collection.
 *   generatedFields: Fields with origin="generated" from the collection schema.
 *   doc:             Optional document for chunk-picker mode.
 */
export function MetagenPreview({ collectionId, generatedFields, doc }: MetagenPreviewProps) {
  // ── State ─────────────────────────────────────────────────────────────────

  const [selectedField, setSelectedField] = useState<string>(
    generatedFields[0]?.field_name ?? '',
  )
  const [sampleText, setSampleText] = useState('')
  const [chunks, setChunks]         = useState<ChunkResponse[]>([])
  const [chunksLoaded, setChunksLoaded] = useState(false)
  const [selectedChunkIdx, setSelectedChunkIdx] = useState(0)
  const [useChunkPicker, setUseChunkPicker]     = useState(false)

  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState<MetagenPreviewResponse | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [error, setError]       = useState<string | null>(null)

  // ── Chunk loading (deferred until the user switches to chunk-picker mode) ──

  async function loadChunks(): Promise<void> {
    if (chunksLoaded || !doc) return
    try {
      const res = await listChunks(collectionId, doc.id, { limit: 200 })
      setChunks(res.chunks)
      setChunksLoaded(true)
    } catch {
      // Non-critical — chunk picker degrades gracefully.
    }
  }

  function handleToggleChunkPicker(on: boolean): void {
    setUseChunkPicker(on)
    if (on) void loadChunks()
  }

  // ── Preview call ─────────────────────────────────────────────────────────

  /**
   * Run the preview call with the current field + input (sample_text or chunk_id).
   */
  async function handlePreview(): Promise<void> {
    setResult(null)
    setUnavailable(false)
    setError(null)

    if (!selectedField) {
      setError('Select a generated field first.')
      return
    }

    const body = useChunkPicker && chunks[selectedChunkIdx]
      ? { field_name: selectedField, chunk_id: chunks[selectedChunkIdx].id }
      : { field_name: selectedField, sample_text: sampleText || '(no sample text provided)' }

    setLoading(true)
    try {
      const res = await previewMetagen(collectionId, body)
      setResult(res)
    } catch (err) {
      // 422: no LLM provider or no target configured — show calm unavailable note.
      if (err instanceof HttpError && err.status === 422) {
        setUnavailable(true)
      } else {
        setError(err instanceof Error ? err.message : 'Preview failed.')
      }
    } finally {
      setLoading(false)
    }
  }

  // ── Empty state: no generated fields ─────────────────────────────────────

  if (generatedFields.length === 0) {
    return (
      <div className="metagen-preview-empty">
        <span className="text-dim" style={{ fontSize: 12 }}>
          No generated fields defined. Add a metadata field with origin&nbsp;
          <span className="tag meta-tag-llm" style={{ verticalAlign: 'middle' }}>generated</span>
          &nbsp;in the Ingest conditions panel, then configure a prompt in the Targets list above.
        </span>
      </div>
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const selectedChunk = chunks[selectedChunkIdx]

  return (
    <div className="metagen-preview">
      {/* ── Field selector ── */}
      <div className="metagen-preview-row">
        <label className="metagen-preview-label" htmlFor="metagen-field-select">
          Field
        </label>
        <select
          id="metagen-field-select"
          className="input select"
          style={{ flex: 1, fontSize: 12 }}
          value={selectedField}
          onChange={e => {
            setSelectedField(e.target.value)
            setResult(null)
            setUnavailable(false)
          }}
        >
          {generatedFields.map(f => (
            <option key={f.field_name} value={f.field_name}>
              {f.field_name} ({f.field_type})
            </option>
          ))}
        </select>
      </div>

      {/* ── Input mode toggle (chunk-picker only when doc is provided + done) ── */}
      {doc && doc.status === 'done' && (
        <div className="metagen-preview-row" style={{ gap: 6 }}>
          <button
            type="button"
            className={`chip${!useChunkPicker ? ' chip-active' : ''}`}
            onClick={() => handleToggleChunkPicker(false)}
          >
            Sample text
          </button>
          <button
            type="button"
            className={`chip${useChunkPicker ? ' chip-active' : ''}`}
            onClick={() => handleToggleChunkPicker(true)}
          >
            Pick a chunk
          </button>
        </div>
      )}

      {/* ── Sample text input (shown when not in chunk-picker mode) ── */}
      {!useChunkPicker && (
        <textarea
          className="input"
          rows={4}
          style={{ resize: 'vertical', fontSize: 12 }}
          placeholder="Paste a representative text snippet here — the LLM will generate the field value from this."
          value={sampleText}
          onChange={e => setSampleText(e.target.value)}
        />
      )}

      {/* ── Chunk picker (shown when useChunkPicker + chunks loaded) ── */}
      {useChunkPicker && (
        <div className="metagen-preview-chunk-picker">
          {!chunksLoaded ? (
            <span className="text-muted" style={{ fontSize: 11 }}>Loading chunks…</span>
          ) : chunks.length === 0 ? (
            <span className="text-dim" style={{ fontSize: 11 }}>No chunks found for this document.</span>
          ) : (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={selectedChunkIdx === 0}
                onClick={() => setSelectedChunkIdx(i => Math.max(0, i - 1))}
                style={{ fontSize: 11 }}
              >
                prev
              </button>
              <select
                className="input select"
                value={selectedChunkIdx}
                onChange={e => setSelectedChunkIdx(parseInt(e.target.value, 10))}
                style={{ flex: 1, fontSize: 11 }}
              >
                {chunks.map((c, i) => (
                  <option key={c.id} value={i}>
                    #{i + 1} · {c.strategy} · {c.token_count} tok · {c.raw_text.slice(0, 55)}…
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={selectedChunkIdx === chunks.length - 1}
                onClick={() => setSelectedChunkIdx(i => Math.min(chunks.length - 1, i + 1))}
                style={{ fontSize: 11 }}
              >
                next
              </button>
            </div>
          )}
          {/* Show selected chunk body as context */}
          {selectedChunk && (
            <pre className="metagen-preview-chunk-body">{selectedChunk.raw_text.slice(0, 400)}</pre>
          )}
        </div>
      )}

      {/* ── Run button ── */}
      <button
        type="button"
        className="btn btn-primary"
        style={{ marginTop: 4, fontSize: 12 }}
        disabled={loading || !selectedField}
        onClick={() => void handlePreview()}
      >
        {loading ? 'Generating…' : 'Run preview'}
      </button>

      {/* ── Error ── */}
      {error && (
        <div className="error-banner" style={{ marginTop: 8, fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* ── Preview unavailable (422 — no provider or no target) ── */}
      {unavailable && (
        <div className="info-banner" style={{ marginTop: 8, fontSize: 12 }}>
          <span className="info-icon">ℹ</span>
          <span>
            Preview unavailable — configure an LLM provider in the Providers chain and add a
            target with a prompt for <strong>{selectedField}</strong> first.
          </span>
        </div>
      )}

      {/* ── Result ── */}
      {result && (
        <div className="metagen-preview-result">
          {/* Degraded badge */}
          {result.degraded && (
            <div className="warning-banner" style={{ marginBottom: 8, fontSize: 12 }}>
              Degraded result — provider fell back or returned a partial value.
            </div>
          )}

          {/* Generated value */}
          <div className="metagen-preview-value-block">
            <div className="metagen-preview-value-label">Generated value</div>
            <pre className="metagen-preview-value">
              {typeof result.value === 'string'
                ? result.value
                : JSON.stringify(result.value, null, 2)}
            </pre>
          </div>

          {/* Cost / token estimate + provider */}
          <div className="metagen-preview-meta">
            <span className="metagen-preview-meta-item">
              <span className="text-dim">tokens:</span>&nbsp;
              <span className="mono">{result.token_estimate}</span>
            </span>
            <span className="metagen-preview-meta-item">
              <span className="text-dim">cost:</span>&nbsp;
              <span className="mono">${result.cost_estimate.toFixed(5)}</span>
            </span>
            <span className="metagen-preview-meta-item">
              <span className="text-dim">scope:</span>&nbsp;
              <span className="tag" style={{ fontSize: 10 }}>{result.scope}</span>
            </span>
            <span className="metagen-preview-meta-item">
              <span className="text-dim">provider:</span>&nbsp;
              <span className="mono">{result.provider}</span>
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
