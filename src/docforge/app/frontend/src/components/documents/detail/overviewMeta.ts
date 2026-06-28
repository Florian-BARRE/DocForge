// ====== Code Summary ======
// Pure metadata helpers for OverviewTab: key-set constants, label overrides,
// and formatting utilities. No React / no JSX.

// ── Key classification sets ───────────────────────────────────────────────────

/** implicit_meta keys that belong in the dedicated Chain traces tab — skip in Overview. */
export const SKIP_IMPLICIT = new Set(['chain_traces', 'embed_chain_traces'])

/** implicit_meta keys shown only in the collapsed "Advanced / internal" section. */
export const INTERNAL_IMPLICIT = new Set([
  'ir_key', 'markdown_key',
  's0_fingerprint', 's1_fingerprint', 's2_fingerprint',
])

// ── Label overrides ───────────────────────────────────────────────────────────

/**
 * Human-readable label overrides for known snake_case implicit_meta keys.
 * Keys not in this map are title-cased automatically by humanize().
 * Acronyms (VLM, OCR, IR, S0–S6) require manual entries here.
 */
export const LABEL: Record<string, string> = {
  vlm_calls: 'VLM calls',           vlm_cache_hits: 'VLM cache hits',
  ocr_calls: 'OCR calls',           ocr_cache_hits: 'OCR cache hits',
  classifier_calls: 'Classifier calls',
  figures_enriched: 'Figures enriched',
  chart_extractions: 'Chart extractions',
  budget_spent: 'Budget spent',
  n_figures: 'Figures',             n_tables: 'Tables',
  has_scanned_pages: 'Scanned pages',
  ir_key: 'IR key',                 markdown_key: 'Markdown key',
  s0_fingerprint: 'S0 fingerprint',
  s1_fingerprint: 'S1 fingerprint',
  s2_fingerprint: 'S2 fingerprint',
}

// ── Formatting helpers ────────────────────────────────────────────────────────

/**
 * Converts a snake_case key to Title Case, applying LABEL overrides first.
 * Handles known acronyms (VLM, OCR, IR, S0-S6) via the LABEL map.
 *
 * Args:
 *   k: Snake_case metadata key.
 *
 * Returns:
 *   Human-readable label string.
 */
export function humanize(k: string): string {
  return LABEL[k] ?? k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

/**
 * Formats a budget_spent number as a USD amount string with appropriate precision.
 *
 * Args:
 *   v: Cost in USD (typically a small float).
 *
 * Returns:
 *   Formatted string such as "$0.00120" or "$0.0042".
 */
export function formatBudget(v: number): string {
  if (v === 0) return '$0.00'
  return v < 0.001 ? `$${v.toFixed(5)}` : `$${v.toFixed(4)}`
}

/**
 * Returns the length of v if it is an array, otherwise 0.
 * Used to count chain trace / embed trace entries from either location.
 *
 * Args:
 *   v: Any value that might be an array.
 *
 * Returns:
 *   Array length or 0.
 */
export function countArr(v: unknown): number {
  return Array.isArray(v) ? v.length : 0
}
