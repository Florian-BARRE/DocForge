// ====== Code Summary ======
// Identifies the bootstrap/root key so its revoke/rotate actions can require a typed confirmation
// (losing it can lock an operator out of key management entirely — see RootKeyConfirmGate).

import type { ApiKeyInfo } from "../../api/auth";

// Mirrors the backend's fixed bootstrap account/key name (`_ROOT_USERNAME` in
// app/backend/libs/auth/bootstrap.py). The API never exposes an explicit "is root" flag on
// `KeyInfo`, so the exact name is the only signal available from the frontend. A user-created key
// deliberately named "root" would also match — an acceptable false positive (extra caution),
// never a false negative.
export const ROOT_KEY_NAME = "root";

/** Whether `apiKey` is (or matches the name of) the bootstrap root key. */
export function isRootKey(apiKey: Pick<ApiKeyInfo, "name">): boolean {
  return apiKey.name === ROOT_KEY_NAME;
}
