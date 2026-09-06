// ====== Code Summary ======
// Shared worker-liveness helpers — the two-signal state (alive/busy → busy/idle/offline), its
// tone color, and the relative-time formatters used by both WorkerCard (Workers page) and
// WorkerLiveCard (Monitoring page's live dashboard) so the two surfaces read identically.

import type { WorkerActivity } from "../../api/jobs";
import { theme } from "../../theme";

export type Liveness = "busy" | "idle" | "offline";

export function liveness(activity: WorkerActivity): Liveness {
  if (!activity.alive) return "offline";
  return activity.busy ? "busy" : "idle";
}

// Busy = the one thing being worked → forge orange. Idle-alive = present but at rest → neutral
// steel (never green — green is reserved for "done"). Offline = absent → muted warm grey.
export const LIVENESS_COLOR: Record<Liveness, string> = {
  busy: theme.color.accent,
  idle: theme.color.info,
  offline: theme.color.mute,
};

/** Relative "Xs/Xm ago" since a timestamp, or a fallback when none was ever recorded. */
export function formatSince(value: string | null): string {
  if (!value) return "no heartbeat recorded";
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

/** Process uptime since `started_at` — "3h 12m" / "42m" style, or "—" when never registered. */
export function formatUptime(startedAt: string | null): string {
  if (!startedAt) return "—";
  const seconds = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
