// ====== Code Summary ======
// LabDebugPanel — rich debug panel shown after every Search Lab query.
// Always visible (lab always sends debug:true).  Reads the `effective` sub-object
// from debug_info to show the actual settings the backend applied, the recall
// funnel (candidates → top_k), and the query variants when a transform ran.

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Local Project Imports ======
import type { SearchEffective } from './labTypes'

// ── Types ─────────────────────────────────────────────────────────────────────

interface LabDebugPanelProps {
  /** Raw debug_info payload from the last SearchResponse. */
  debugInfo: Record<string, unknown> | null
  /** top_k requested — used to show the recall funnel. */
  topK: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract a SearchEffective from the raw debug_info payload.
 *
 * Reads from `debug_info.effective` first (new backend format), then falls
 * back to flat keys on debug_info for backward compatibility.
 *
 * Args:
 *   debugInfo: Raw debug_info from the search response.
 *
 * Returns:
 *   SearchEffective: The resolved effective settings.
 */
function extractEffective(debugInfo: Record<string, unknown>): SearchEffective {
  const eff = (debugInfo.effective as Record<string, unknown> | undefined) ?? debugInfo
  return {
    vector_mode:               asString(eff.vector_mode),
    fusion:                    asString(eff.fusion),
    query_transform_strategy:  asString(eff.query_transform_strategy ?? eff.strategy),
    rerank_enabled:            asBoolean(eff.rerank_enabled),
    sparse_enabled:            asBoolean(eff.sparse_enabled),
    candidate_count:           asNumber(eff.candidate_count ?? debugInfo.candidate_limit),
    query_variants:            asStringArray(eff.query_variants ?? debugInfo.query_variants),
    reranked:                  asBoolean(eff.reranked),
  }
}

/** Build chip label list from the effective object. */
function buildChips(eff: SearchEffective): string[] {
  const chips: string[] = []
  if (eff.vector_mode) chips.push(eff.vector_mode)
  if (eff.fusion) chips.push(eff.fusion.toUpperCase())
  if (eff.query_transform_strategy && eff.query_transform_strategy !== 'none')
    chips.push(eff.query_transform_strategy)
  chips.push(`rerank ${eff.rerank_enabled ? 'ON' : 'OFF'}`)
  return chips
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Rich debug panel for the Search Lab.
 *
 * Renders three information layers, all read from debug_info:
 *   1. Effective chips — actual settings applied by the backend (mode / fusion /
 *      transform / rerank status). Uses `debug_info.effective` with a flat
 *      fallback for backward compat.
 *   2. Recall funnel — retrieved N candidates → top_k returned.
 *   3. Query variants — count + list when a transform generated variants.
 *
 * Args:
 *   debugInfo: Raw debug_info from the last SearchResponse.
 *   topK:      The top_k value sent in the request.
 */
export function LabDebugPanel({ debugInfo, topK }: LabDebugPanelProps) {
  const [variantsOpen, setVariantsOpen] = useState(false)

  // 1. Nothing to render without a debug payload.
  if (!debugInfo) return null

  // 2. Extract effective settings.
  const eff = extractEffective(debugInfo)
  const chips = buildChips(eff)

  // 3. Variant list — show all including the original; count drives the toggle label.
  const allVariants = eff.query_variants ?? []
  const variantCount = allVariants.length

  return (
    <div className="lab-debug-panel">
      {/* ── Header ── */}
      <div className="lab-debug-header">
        <span className="lab-debug-title">Effective</span>
        {eff.reranked && (
          <span className="tag tag-done" style={{ fontSize: 9 }}>reranked</span>
        )}
        {eff.sparse_enabled === false && (
          <span className="tag" style={{ fontSize: 9 }}>BM25 unavailable</span>
        )}
      </div>

      {/* ── Effective chips ── */}
      <div className="lab-effective-bar">
        {chips.map(chip => (
          <span key={chip} className="lab-effective-chip">{chip}</span>
        ))}
      </div>

      {/* ── Recall funnel ── */}
      {eff.candidate_count != null && (
        <div className="lab-recall-hint">
          Retrieved {eff.candidate_count} candidates &rarr; top {topK} returned
          {eff.reranked ? ' (cross-encoder reranked)' : ''}
        </div>
      )}

      {/* ── Query variants ── */}
      {variantCount > 1 && (
        <div style={{ marginTop: 6 }}>
          <button
            type="button"
            className="lab-tuning-toggle"
            style={{ padding: '2px 0', background: 'none', borderRadius: 0 }}
            onClick={() => setVariantsOpen(o => !o)}
          >
            <span className="metadata-form-chevron">{variantsOpen ? '▾' : '▸'}</span>
            <span className="lab-debug-title">{variantCount} query variants</span>
          </button>
          {variantsOpen && (
            <div className="lab-variants-list">
              {allVariants.map((v, i) => (
                <span key={i} className="lab-variant-chip">
                  {i === 0 ? '(original) ' : ''}{v}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Type coercions ────────────────────────────────────────────────────────────

function asString(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

function asNumber(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

function asBoolean(v: unknown): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined
}

function asStringArray(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined
  const filtered = v.filter((x): x is string => typeof x === 'string')
  return filtered.length > 0 ? filtered : undefined
}
