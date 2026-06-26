// ====== Code Summary ======
// Permission helpers — derive what the current root session is allowed to do.
//
// AUTH-B simplified model: the UI is root-only so all permission checks reduce
// to "is the user non-null and is their role root?".  The helpers are kept as
// thin wrappers so the prop-threading pattern in AppShell (write → DocumentsTab
// and PipelineTab) remains explicit and testable.

import type { UserSummary } from '../api/types'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns true when the user can ingest, reingest, update, or delete documents.
 *
 * In the simplified auth model the UI is root-only, so this reduces to a
 * non-null root role check.
 *
 * Args:
 *   user: Current authenticated user summary, or null when logged out.
 *
 * Returns:
 *   True if the user is root (can write everywhere).
 */
export function canWrite(user: UserSummary | null): boolean {
  return user?.role === 'root'
}
