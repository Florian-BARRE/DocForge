// ====== Code Summary ======
// Reads the deployment's auth-enforcement state from the public GET /capabilities (see
// api/capabilities.ts) — the single source the auth-off banner + TokenControl both key off of, so
// neither hardcodes a guess about whether the backend actually enforces API keys.

import { useEffect, useState } from "react";
import { getCapabilities } from "../../api/capabilities";

/**
 * Whether this deployment currently enforces API-key bearer auth.
 *
 * Returns:
 *     boolean | null: `null` while loading or if the capabilities probe itself failed — callers
 *     must treat `null` as "unknown", never as "auth is off" (a failed probe says nothing about
 *     the deployment's real auth state).
 */
export function useAuthEnabled(): boolean | null {
  const [authEnabled, setAuthEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCapabilities()
      .then((capabilities) => {
        if (!cancelled) setAuthEnabled(capabilities.auth_enabled);
      })
      .catch(() => {
        // Best-effort — a probe failure just leaves the state "unknown", never blocks the page.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return authEnabled;
}
