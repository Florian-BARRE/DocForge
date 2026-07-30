// ====== Code Summary ======
// The expiry-state chip for a key row — no-expiry / expired / expiring-soon / expiring-later. An
// expired-but-not-revoked key is still effectively dead, so it gets the same "error" tone revoked
// keys would.

import { Chip, type ChipTone } from "../../components/Chip";
import { daysUntil, humanizeUntil } from "./relativeTime";

const EXPIRY_WARN_THRESHOLD_DAYS = 7;

interface ExpiryChipProps {
  expiresAt: string | null;
}

export function ExpiryChip({ expiresAt }: ExpiryChipProps) {
  if (!expiresAt) return <Chip tone="neutral">no expiry</Chip>;

  const remaining = daysUntil(expiresAt);
  if (remaining < 0) return <Chip tone="error">expired</Chip>;

  const tone: ChipTone = remaining <= EXPIRY_WARN_THRESHOLD_DAYS ? "warn" : "ok";
  return <Chip tone={tone}>expires {humanizeUntil(expiresAt)}</Chip>;
}
