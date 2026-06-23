// ====== Code Summary ======
// Shared helpers and types for the search stage configuration sections. Holds the
// `extractSearchCfg` accessor and the `TransformStrategy` type used by the
// dispatcher (SearchStagePanel) and the individual section components.

// ====== Internal Project Imports ======
import type { ConfigState } from '../../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Strategy type shared by several helpers. */
export type TransformStrategy = 'none' | 'rewrite' | 'hyde' | 'multi_query'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract the `pipeline.search` sub-object from a ConfigState instance.
 *
 * Args:
 *   cfg: Current collection config state or null.
 *
 * Returns:
 *   Record<string, unknown>: The search sub-config, or an empty object when absent.
 */
export function extractSearchCfg(cfg: ConfigState | null): Record<string, unknown> {
  if (!cfg) return {}
  const pipeline = cfg.pipeline as Record<string, unknown>
  return (pipeline?.search as Record<string, unknown>) ?? {}
}
