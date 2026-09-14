// ====== Code Summary ======
// Reads this deployment's version from the public GET /capabilities (see api/capabilities.ts) — the
// sidebar footer's always-visible "deployment info" line. A full Settings ▸ Deployment page (GPU/
// reachable-sidecars/available-kinds) is a later wave; this hook only surfaces the one field needed
// for the footer today.

import { useEffect, useState } from "react";
import { getCapabilities } from "../api/capabilities";

/**
 * The running deployment's version string, or null while loading / if the probe failed.
 *
 * Returns:
 *     string | null: `null` while loading or on a failed probe — callers must render a neutral
 *     placeholder, never guess a version.
 */
export function useDeploymentVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCapabilities()
      .then((capabilities) => {
        if (!cancelled) setVersion(capabilities.version);
      })
      .catch(() => {
        // Best-effort — a probe failure just leaves the footer's version line blank.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}
