// ====== Code Summary ======
// The "stale" hygiene chip — shown on an active key that has gone unused past the thresholds in
// keyHealth.ts. It renders nothing for a fresh or terminal key, so callers can drop it in
// unconditionally next to the status/expiry chips.

import type { ApiKeyInfo } from "../../api/auth";
import { Chip } from "../../components/Chip";
import { isStale } from "./keyHealth";

interface StaleChipProps {
  apiKey: ApiKeyInfo;
}

export function StaleChip({ apiKey }: StaleChipProps) {
  if (!isStale(apiKey)) return null;
  return (
    <Chip tone="warn" title="Unused past the idle threshold — consider revoking it.">
      stale
    </Chip>
  );
}
