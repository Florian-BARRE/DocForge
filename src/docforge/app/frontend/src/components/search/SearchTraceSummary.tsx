// ====== Code Summary ======
// SearchTraceSummary — collapsible panel (closed by default) that surfaces the
// backend debug_info of the last search in a readable form: vector mode, fusion,
// queried vectors, fusion weights, candidate pool, query variants, and the
// rerank/grouping/MMR toggles. Makes the retrieval pipeline transparent.

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchTraceSummaryProps {
  /** Raw debug_info payload from the last SearchResponse (debug mode), or null. */
  debugInfo: Record<string, unknown> | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Collapsible "Détails de la recherche" panel built from the backend debug_info.
 *
 * Every key is optional — the panel renders only the rows it can populate, so it
 * stays robust against partial or future debug payloads. Closed by default;
 * the header toggle expands it on click.
 *
 * Args:
 *   debugInfo: The last search's debug_info map, or null when unavailable.
 */
export function SearchTraceSummary({ debugInfo }: SearchTraceSummaryProps) {
  const [open, setOpen] = useState(false)

  // 1. Nothing to show without a debug payload.
  if (!debugInfo) return null

  // 2. Read each field defensively (all optional, unknown-typed).
  const vectorMode = asString(debugInfo.vector_mode) ?? 'hybrid'
  const fusion = asString(debugInfo.fusion) ?? 'rrf'
  const rrfK = asNumber(debugInfo.rrf_k)
  const denseVectors = asStringArray(debugInfo.dense_vectors)
  const sparseVectors = asStringArray(debugInfo.sparse_vectors)
  const weights = asNumberMap(debugInfo.weights)
  const candidateLimit = asNumber(debugInfo.candidate_limit)
  const scoreThreshold = asNumber(debugInfo.score_threshold)
  const queryVariants = asStringArray(debugInfo.query_variants)
  const sparseEnabled = debugInfo.sparse_enabled
  const rerankEnabled = Boolean(debugInfo.rerank_enabled)
  const groupingEnabled = Boolean(debugInfo.grouping_enabled)
  const mmrEnabled = Boolean(debugInfo.mmr_enabled)

  // 3. Combine the queried vectors for display.
  const allVectors = [...denseVectors, ...sparseVectors]

  return (
    <div className="search-trace-summary">
      {/* Toggle header */}
      <button
        type="button"
        className="metadata-form-toggle search-trace-summary-toggle"
        onClick={() => setOpen(o => !o)}
      >
        <span className="metadata-form-chevron">{open ? '▾' : '▸'}</span>
        <span className="metadata-form-label">Détails de la recherche</span>
      </button>

      {open && (
        <div className="search-trace-summary-body">
          {/* Vector mode + fusion */}
          <div className="stage-panel-row">
            <span className="stage-panel-label">Mode</span>
            <span className="stage-panel-value">
              {vectorMode} · fusion {fusion.toUpperCase()}
              {fusion === 'rrf' && rrfK !== null ? ` (k=${rrfK})` : ''}
            </span>
          </div>

          {/* Queried vectors */}
          {allVectors.length > 0 && (
            <div className="stage-panel-row">
              <span className="stage-panel-label">Vecteurs</span>
              <span className="stage-panel-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {allVectors.map(v => (
                  <span key={v} className="tag">{v}</span>
                ))}
              </span>
            </div>
          )}

          {/* Fusion weights */}
          {weights && Object.keys(weights).length > 0 && (
            <div className="stage-panel-row">
              <span className="stage-panel-label">Poids</span>
              <span className="stage-panel-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {Object.entries(weights).map(([k, v]) => (
                  <span key={k} className="tag">{k}: {v}</span>
                ))}
              </span>
            </div>
          )}

          {/* Candidate pool */}
          {candidateLimit !== null && (
            <div className="stage-panel-row">
              <span className="stage-panel-label">Candidats</span>
              <span className="stage-panel-value">{candidateLimit}</span>
            </div>
          )}

          {/* Score threshold */}
          {scoreThreshold !== null && (
            <div className="stage-panel-row">
              <span className="stage-panel-label">Seuil</span>
              <span className="stage-panel-value">{scoreThreshold}</span>
            </div>
          )}

          {/* Query variants (only when more than the original query) */}
          {queryVariants.length > 1 && (
            <div className="stage-panel-row">
              <span className="stage-panel-label">Variantes</span>
              <span className="stage-panel-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {queryVariants.map((v, i) => (
                  <span key={i} className="tag">{v}</span>
                ))}
              </span>
            </div>
          )}

          {/* Rerank / grouping / MMR toggles */}
          <div className="stage-panel-row">
            <span className="stage-panel-label">Étapes</span>
            <span className="stage-panel-value" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              <span className={`tag ${rerankEnabled ? 'tag-done' : ''}`}>
                Rerank {rerankEnabled ? 'actif' : 'inactif'}
              </span>
              <span className={`tag ${groupingEnabled ? 'tag-done' : ''}`}>
                Groupage {groupingEnabled ? 'actif' : 'inactif'}
              </span>
              <span className={`tag ${mmrEnabled ? 'tag-done' : ''}`}>
                MMR {mmrEnabled ? 'actif' : 'inactif'}
              </span>
            </span>
          </div>

          {/* Reminder when BM25 is unavailable on a dense-only provider */}
          {sparseEnabled === false && vectorMode !== 'dense' && (
            <div className="stage-panel-row">
              <span className="stage-panel-label" />
              <span className="stage-panel-value text-dim" style={{ fontSize: 11 }}>
                BM25 inactif (provider dense-only)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Coerce an unknown value to a string, or null when not a string.
 *
 * Args:
 *   value: Arbitrary value from the debug payload.
 *
 * Returns:
 *   string | null: The string value, or null.
 */
function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

/**
 * Coerce an unknown value to a finite number, or null otherwise.
 *
 * Args:
 *   value: Arbitrary value from the debug payload.
 *
 * Returns:
 *   number | null: The numeric value, or null.
 */
function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * Coerce an unknown value to an array of strings, dropping non-string entries.
 *
 * Args:
 *   value: Arbitrary value from the debug payload.
 *
 * Returns:
 *   string[]: The list of string entries (empty when not an array).
 */
function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((v): v is string => typeof v === 'string')
}

/**
 * Coerce an unknown value to a numeric map, or null when not a plain object.
 *
 * Args:
 *   value: Arbitrary value from the debug payload.
 *
 * Returns:
 *   Record<string, number> | null: The numeric map, or null.
 */
function asNumberMap(value: unknown): Record<string, number> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v
  }
  return out
}
