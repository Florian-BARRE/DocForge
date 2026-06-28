// ====== Code Summary ======
// LabDebugPanel — collapsible rich debug panel shown after every Search Lab query.
// Always sends debug:true so the panel is always populated after a search.
// Collapsed by default to keep results visible; the header always shows the
// effective chips so context is readable at a glance without expanding.
// The body contains the recall funnel and query variant details.

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
 * `query_variants` handling: the current backend sends an integer COUNT, not a
 * string array.  We try asNumber first; if the value is a string array (old
 * backends), we store the strings and derive the count from `.length`.
 *
 * Args:
 *   debugInfo: Raw debug_info from the search response.
 *
 * Returns:
 *   SearchEffective: The resolved effective settings.
 */
function extractEffective(debugInfo: Record<string, unknown>): SearchEffective {
  const eff = (debugInfo.effective as Record<string, unknown> | undefined) ?? debugInfo
  const rawVariants = eff.query_variants ?? debugInfo.query_variants
  // New backend: integer count.  Old backend: string array.
  const variantCount   = asNumber(rawVariants)
  const variantStrings = asStringArray(rawVariants)
  return {
    vector_mode:               asString(eff.vector_mode),
    fusion:                    asString(eff.fusion),
    query_transform_strategy:  asString(eff.query_transform_strategy ?? eff.strategy),
    rerank_enabled:            asBoolean(eff.rerank_enabled),
    sparse_enabled:            asBoolean(eff.sparse_enabled),
    candidate_count:           asNumber(eff.candidate_count ?? debugInfo.candidate_limit),
    // Integer count wins; fall back to string array length for old backends.
    query_variant_count:       variantCount ?? variantStrings?.length,
    query_variants:            variantStrings,
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
 * Collapsible debug panel for the Search Lab.
 *
 * Collapsed by default so search results are immediately visible.
 * The header always shows the effective chips (mode / fusion / transform /
 * rerank), so the user can read the actual settings at a glance.
 *
 * When expanded, the body adds:
 *   1. Recall funnel — retrieved N candidates → top_k returned.
 *   2. Query variants — count + list when a transform generated variants.
 *
 * Args:
 *   debugInfo: Raw debug_info from the last SearchResponse.
 *   topK:      The top_k value sent in the request.
 */
export function LabDebugPanel({ debugInfo, topK }: LabDebugPanelProps) {
  // Collapsed by default — results are more important than debug metadata.
  const [collapsed, setCollapsed] = useState(true)
  const [variantsOpen, setVariantsOpen] = useState(false)

  // 1. Nothing to render without a debug payload.
  if (!debugInfo) return null

  // 2. Extract effective settings.
  const eff = extractEffective(debugInfo)
  const chips = buildChips(eff)

  // 3. Resolve variant count.
  const variantCount   = eff.query_variant_count ?? 0
  const variantStrings = eff.query_variants ?? []

  return (
    <div className="lab-debug-panel">
      {/* ── Header — always visible, click to expand/collapse ── */}
      <button
        type="button"
        className="lab-debug-toggle"
        onClick={() => setCollapsed(o => !o)}
        aria-expanded={!collapsed}
      >
        <span className="metadata-form-chevron">{collapsed ? '▸' : '▾'}</span>
        <span className="lab-debug-title">Effective</span>
        {/* Effective chips always visible — compact summary even when collapsed. */}
        <div className="lab-effective-bar lab-effective-bar-inline">
          {chips.map(chip => (
            <span key={chip} className="lab-effective-chip">{chip}</span>
          ))}
        </div>
        {/* Status tags in the header */}
        {eff.reranked && (
          <span className="tag tag-done" style={{ fontSize: 9, flexShrink: 0 }}>reranked</span>
        )}
        {eff.sparse_enabled === false && (
          <span className="tag" style={{ fontSize: 9, flexShrink: 0 }}>BM25 unavailable</span>
        )}
      </button>

      {/* ── Body — only shown when expanded ── */}
      {!collapsed && (
        <div className="lab-debug-body">
          {/* Recall funnel */}
          {eff.candidate_count != null && (
            <div className="lab-recall-hint">
              Retrieved {eff.candidate_count} candidates &rarr; top {topK} returned
              {eff.reranked ? ' (cross-encoder reranked)' : ''}
            </div>
          )}

          {/* Query variants count (new backend: integer) */}
          {variantCount > 1 && (
            <div className="lab-recall-hint">
              Query variants: {variantCount}
            </div>
          )}

          {/* Query variant strings (old backends that send the actual array) */}
          {variantStrings.length > 1 && (
            <div style={{ marginTop: 6 }}>
              <button
                type="button"
                className="lab-tuning-toggle"
                style={{ padding: '2px 0', background: 'none', borderRadius: 0 }}
                onClick={() => setVariantsOpen(o => !o)}
              >
                <span className="metadata-form-chevron">{variantsOpen ? '▾' : '▸'}</span>
                <span className="lab-debug-title">{variantStrings.length} query variants</span>
              </button>
              {variantsOpen && (
                <div className="lab-variants-list">
                  {variantStrings.map((v, i) => (
                    <span key={i} className="lab-variant-chip">
                      {i === 0 ? '(original) ' : ''}{v}
                    </span>
                  ))}
                </div>
              )}
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
