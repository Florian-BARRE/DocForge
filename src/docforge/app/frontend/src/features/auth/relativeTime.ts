// ====== Code Summary ======
// Local time-humanizing helpers for the auth feature (features/ never cross-import — see
// collections/relativeTime.ts for the sibling "ago" copy). This one also covers the forward
// direction ("expires in") the expiry badge needs, which the collections helper doesn't.

/**
 * Coarsen a non-negative delta in seconds into the largest sensible unit label ("42m", "3h", "5d").
 *
 * @param deltaSeconds - A non-negative duration, in seconds.
 * @returns A short unit-suffixed label.
 */
function humanizeDuration(deltaSeconds: number): string {
  if (deltaSeconds < 60) return "moments";

  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m`;

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h`;

  const deltaDays = Math.floor(deltaHours / 24);
  return `${deltaDays}d`;
}

/**
 * Humanize a past ISO timestamp as "just now" / "Xm ago" / "Xh ago" / "Xd ago".
 *
 * @param iso - An ISO-8601 timestamp, or `null`.
 * @returns A short "ago" label, or "—" for `null`.
 */
export function humanizeAgo(iso: string | null): string {
  if (!iso) return "—";
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (deltaSeconds < 60) return "just now";
  return `${humanizeDuration(deltaSeconds)} ago`;
}

/**
 * Humanize a future ISO timestamp as "in Xd" / "in Xh" — used for expiry countdowns.
 *
 * @param iso - A future ISO-8601 timestamp.
 * @returns A short "in X" label.
 */
export function humanizeUntil(iso: string): string {
  const deltaSeconds = Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000));
  return `in ${humanizeDuration(deltaSeconds)}`;
}

/**
 * Days remaining until an ISO instant (negative once past) — drives the expiry badge's tone.
 *
 * @param iso - An ISO-8601 timestamp.
 * @returns The (possibly fractional, possibly negative) number of days until `iso`.
 */
export function daysUntil(iso: string): number {
  return (new Date(iso).getTime() - Date.now()) / (1000 * 60 * 60 * 24);
}
