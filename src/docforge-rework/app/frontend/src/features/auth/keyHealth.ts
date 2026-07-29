// ====== Code Summary ======
// Pure staleness rule for an API key — a hygiene signal that surfaces keys worth pruning. Kept
// side-effect-free (the reference instant is injectable) so it is trivially unit-testable and the
// same rule drives both the list row and the detail page.

import type { ApiKeyInfo } from "../../api/auth";

const NEVER_USED_GRACE_DAYS = 30;
const IDLE_DAYS = 90;
const MS_PER_DAY = 1000 * 60 * 60 * 24;

/**
 * Decide whether an active key looks stale enough to consider revoking.
 *
 * A key is stale when it has either never been used yet was created more than 30 days ago, or was
 * last used more than 90 days ago. Revoked keys are terminal and expired keys are already flagged
 * by the expiry badge, so neither is ever reported stale.
 *
 * @param key - The key to assess.
 * @param now - The reference instant (injectable for tests; defaults to the current time).
 * @returns True when the key is active and idle past the thresholds above.
 */
export function isStale(key: ApiKeyInfo, now: Date = new Date()): boolean {
  // 1. Terminal keys never warrant a prune hint — revocation already handled them.
  if (key.revoked_at) return false;

  const nowMs = now.getTime();

  // 2. Never used: stale only once the creation grace period has elapsed.
  if (!key.last_used_at) {
    if (!key.created_at) return false;
    return nowMs - new Date(key.created_at).getTime() > NEVER_USED_GRACE_DAYS * MS_PER_DAY;
  }

  // 3. Used, but idle beyond the tolerance window.
  return nowMs - new Date(key.last_used_at).getTime() > IDLE_DAYS * MS_PER_DAY;
}
