// ====== Code Summary ======
// UI-level constants and derived types for the API key permission builder.
// The Capability, PermissionRole, PermissionEntry, and Permissions wire types
// live in api/types.ts; this file extends them with presentation helpers.

import type { Capability, PermissionRole } from '../../api/types'

// ── Capability taxonomy ───────────────────────────────────────────────────────
//
// Hardcoded on the frontend — the taxonomy is small and stable; it mirrors
// the capability set defined in the design doc (auth-keys-only/design.md).

/** Display labels for each fine-grained capability. */
export const CAPABILITY_LABELS: Record<Capability, string> = {
  'documents.read':   'Read documents',
  'documents.write':  'Write documents',
  'search':           'Search',
  'config.read':      'Read config',
  'config.write':     'Write config',
  'chunks.write':     'Edit chunks',
  'collection.admin': 'Collection admin',
}

/** Ordered list of all capabilities for rendering checkboxes. */
export const ALL_CAPABILITIES: Capability[] = [
  'documents.read',
  'documents.write',
  'search',
  'config.read',
  'config.write',
  'chunks.write',
  'collection.admin',
]

/** Capability sets for each role shortcut. */
export const ROLE_CAPABILITIES: Record<Exclude<PermissionRole, 'custom'>, Capability[]> = {
  read:  ['documents.read', 'search', 'config.read'],
  write: ['documents.read', 'search', 'config.read', 'documents.write', 'config.write', 'chunks.write'],
  admin: ['documents.read', 'search', 'config.read', 'documents.write', 'config.write', 'chunks.write', 'collection.admin'],
}

// ── PermissionRowDraft ────────────────────────────────────────────────────────
//
// Internal builder state for one permission entry row.  This is the mutable
// draft tracked by PermissionBuilder; it is never sent to the backend directly.

/** Draft state for a single permission entry row in the builder. */
export interface PermissionRowDraft {
  /** Stable local key for React reconciliation (never sent to the backend). */
  localId: string
  /** '*' for the all-collections row; a real collection UUID otherwise. */
  collectionId: string
  /** Role shortcut or 'custom' when the user has expanded the capabilities. */
  role: PermissionRole
  /** Only meaningful when role === 'custom'. */
  capabilities: Capability[]
  /** Whether the "Advanced" capability panel is expanded. */
  advancedOpen: boolean
}

// ── Scope summary helper ──────────────────────────────────────────────────────

/**
 * Produces a concise human-readable summary of a key's permission scope.
 *
 * Used in the keys list table — keeps each cell to one short line.
 *
 * Args:
 *   permissions: The permissions object from ApiKeySummary, or null for legacy.
 *   collectionName: Optional function to resolve a collection name from its UUID.
 *
 * Returns:
 *   A short summary string, e.g. "All collections · admin" or "2 scopes".
 */
export function formatScopeSummary(
  permissions: { entries: { collection_id: string; role: string }[] } | null,
  collectionName?: (id: string) => string | undefined,
): string {
  if (!permissions || permissions.entries.length === 0) return 'Full access'
  const { entries } = permissions
  if (entries.length === 1) {
    const e = entries[0]
    const scopeLabel = e.collection_id === '*'
      ? 'All collections'
      : (collectionName?.(e.collection_id) ?? e.collection_id.slice(0, 8) + '…')
    return `${scopeLabel} · ${e.role}`
  }
  // Multiple entries — list them if there are only a few; abbreviate otherwise.
  if (entries.length <= 3) {
    return entries
      .map(e => {
        const label = e.collection_id === '*'
          ? 'All'
          : (collectionName?.(e.collection_id) ?? e.collection_id.slice(0, 6) + '…')
        return `${label}:${e.role}`
      })
      .join(', ')
  }
  return `${entries.length} scopes`
}
