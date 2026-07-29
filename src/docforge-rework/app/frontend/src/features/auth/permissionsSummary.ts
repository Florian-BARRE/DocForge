// ====== Code Summary ======
// Formats a key's `permissions` into the one-line summary shown in the list — "full access" for
// `null`, otherwise the capability list plus the scoped collections spelled out by NAME (falling
// back to a short id slice for anything the collections fetch didn't resolve).

import { ALL_COLLECTIONS_SCOPE, type KeyPermissions } from "../../api/auth";

const MAX_NAMED_COLLECTIONS = 3;

/**
 * Describe a permission grant's collection scope by name.
 *
 * @param collections - The raw scope list from `KeyPermissions.collections` (`["*"]` or UUIDs).
 * @param collectionNames - Best-effort id→name map (a failed collections fetch just yields id slices).
 * @returns "all collections", a comma-joined name list (capped at 3, "+N more"), or "no collections".
 */
function describeCollectionsScope(collections: string[], collectionNames: Map<string, string>): string {
  if (collections.includes(ALL_COLLECTIONS_SCOPE)) return "all collections";
  if (collections.length === 0) return "no collections";

  const names = collections.map((id) => collectionNames.get(id) ?? `${id.slice(0, 8)}…`);
  const shown = names.slice(0, MAX_NAMED_COLLECTIONS).join(", ");
  const remaining = names.length - MAX_NAMED_COLLECTIONS;
  return remaining > 0 ? `${shown} +${remaining} more` : shown;
}

/**
 * Format a key's `permissions` into the one-line summary shown in its row.
 *
 * @param permissions - `null` means unrestricted full access.
 * @param collectionNames - Best-effort id→name map for the scoped-collections branch.
 * @returns e.g. "full access", or "read, search · DemoCollection, Invoices".
 */
export function describeScope(permissions: KeyPermissions | null, collectionNames: Map<string, string>): string {
  if (!permissions) return "full access";

  const capabilities = permissions.capabilities.length > 0 ? permissions.capabilities.join(", ") : "no capability";
  return `${capabilities} · ${describeCollectionsScope(permissions.collections, collectionNames)}`;
}
