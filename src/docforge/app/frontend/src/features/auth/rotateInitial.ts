// ====== Code Summary ======
// Derive a CreateKeyForm "rotate" pre-fill from the key being rotated. Shared by the keys list and
// the key detail page (both offer rotate), kept in one place so the two entry points stay in sync.

import { ALL_COLLECTIONS_SCOPE, type ApiCapability, type ApiKeyInfo } from "../../api/auth";
import type { CreateKeyFormInitial } from "./CreateKeyForm";
import { isoToExpiryChoice } from "./expiry";

/**
 * Replace a pre-split key's legacy `read` with the two halves it is equivalent to, so the rotate
 * form (which only offers the canonical capabilities) pre-checks exactly what the key can do.
 *
 * @param capabilities - The stored capability list.
 * @returns The list with `read` expanded to `read_text` + `read_technical`, de-duplicated.
 */
function expandLegacyRead(capabilities: ApiCapability[]): ApiCapability[] {
  const expanded = capabilities.flatMap((c): ApiCapability[] => (c === "read" ? ["read_text", "read_technical"] : [c]));
  return [...new Set(expanded)];
}

/**
 * Build the rotate-mode initial state from the key it replaces — same name, permissions and expiry,
 * editable before submit (the backend clones omitted fields, but the UI always sends a full override).
 *
 * @param key - The key selected for rotation.
 * @returns The `CreateKeyForm` initial state for "rotate" mode.
 */
export function deriveRotateInitial(key: ApiKeyInfo): CreateKeyFormInitial {
  const permissions = key.permissions;
  return {
    name: key.name,
    fullAccess: permissions === null,
    profile: permissions?.profile ?? null,
    capabilities: expandLegacyRead(permissions?.capabilities ?? []),
    collectionsScope:
      !permissions || permissions.collections.includes(ALL_COLLECTIONS_SCOPE) ? "all" : permissions.collections,
    expiry: isoToExpiryChoice(key.expires_at),
  };
}
