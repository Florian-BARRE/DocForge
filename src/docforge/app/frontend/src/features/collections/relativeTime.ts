// ====== Code Summary ======
// A tiny humanizer for ISO timestamps into "3m ago" / "2h ago" style labels — used wherever a
// dashboard needs to show recency without a full date/time string.

/**
 * Humanize an ISO timestamp as a coarse relative-time label.
 *
 * @param iso - An ISO-8601 timestamp, or null when the event hasn't happened yet.
 * @returns A short "just now" / "Xm ago" / "Xh ago" / "Xd ago" label, or "—" when `iso` is null.
 */
export function humanizeRelativeTime(iso: string | null): string {
  if (!iso) return "—";

  // 1. Coarsen the delta to seconds, then bucket into the largest sensible unit.
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (deltaSeconds < 60) return "just now";

  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;

  const deltaHours = Math.floor(deltaMinutes / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;

  const deltaDays = Math.floor(deltaHours / 24);
  return `${deltaDays}d ago`;
}
