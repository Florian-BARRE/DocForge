// ====== Code Summary ======
// Formats a key's `permissions` into the one-line summary shown in the list — "full access" for
// `null`, otherwise the capability list plus a collection-scope count.

import { ALL_COLLECTIONS_SCOPE, type KeyPermissions } from "../../api/auth";

export function summarizePermissions(permissions: KeyPermissions | null): string {
  if (!permissions) return "full access";

  const capabilities = permissions.capabilities.length > 0 ? permissions.capabilities.join(", ") : "no capability";
  const scope = permissions.collections.includes(ALL_COLLECTIONS_SCOPE)
    ? "all collections"
    : `${permissions.collections.length} collection${permissions.collections.length === 1 ? "" : "s"}`;

  return `${capabilities} · ${scope}`;
}
