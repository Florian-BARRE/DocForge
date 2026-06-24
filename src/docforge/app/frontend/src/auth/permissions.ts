// ====== Code Summary ======
// Permission helpers — derive what the current user is allowed to do on a
// given collection based on their global role and per-collection grants.
// Used by DocumentsTab, PipelineTab, and other views to hide/disable controls.

import type { UserSummary, CollectionGrantSummary } from '../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

export type CollectionRole = 'read' | 'write' | 'admin' | null

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the effective role a user has on a specific collection.
 *
 * Root users have implicit 'admin' everywhere.  For regular users the
 * per-collection grant list is consulted; null is returned when no grant exists.
 *
 * Args:
 *   user:         The current user summary.
 *   grants:       All per-collection grants for the current user.
 *   collectionId: The collection to check.
 *
 * Returns:
 *   The effective role string, or null if the user has no access.
 */
export function getCollectionRole(
  user: UserSummary | null,
  grants: CollectionGrantSummary[],
  collectionId: string | null,
): CollectionRole {
  if (!user || !collectionId) return null
  if (user.role === 'root') return 'admin'
  const grant = grants.find(g => g.collection_id === collectionId)
  return (grant?.role as CollectionRole) ?? null
}

/**
 * Returns true when the user can read documents in the given collection.
 *
 * Any non-null role (read / write / admin) or root grants read access.
 *
 * Args:
 *   user:         Current user.
 *   grants:       Per-collection grants.
 *   collectionId: Target collection.
 *
 * Returns:
 *   True if the user can read.
 */
export function canRead(
  user: UserSummary | null,
  grants: CollectionGrantSummary[],
  collectionId: string | null,
): boolean {
  return getCollectionRole(user, grants, collectionId) !== null
}

/**
 * Returns true when the user can ingest, reingest, update, or delete documents.
 *
 * Requires 'write' or 'admin' role (or root).
 *
 * Args:
 *   user:         Current user.
 *   grants:       Per-collection grants.
 *   collectionId: Target collection.
 *
 * Returns:
 *   True if the user can write.
 */
export function canWrite(
  user: UserSummary | null,
  grants: CollectionGrantSummary[],
  collectionId: string | null,
): boolean {
  const role = getCollectionRole(user, grants, collectionId)
  return role === 'write' || role === 'admin'
}

/**
 * Returns true when the user can manage collection config, reindex, and collaborators.
 *
 * Requires 'admin' role (or root).
 *
 * Args:
 *   user:         Current user.
 *   grants:       Per-collection grants.
 *   collectionId: Target collection.
 *
 * Returns:
 *   True if the user is a collection admin.
 */
export function canAdmin(
  user: UserSummary | null,
  grants: CollectionGrantSummary[],
  collectionId: string | null,
): boolean {
  return getCollectionRole(user, grants, collectionId) === 'admin'
}
