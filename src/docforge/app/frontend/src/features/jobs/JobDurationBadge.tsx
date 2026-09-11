// ====== Code Summary ======
// A job's wall-clock duration, mono per brand.md's "machine values" rule — rendered in the fleet
// list footer. Null (a still-queued job never started) renders nothing rather than "0s", which would
// read as a real elapsed time.

import { theme } from "../../theme";

interface JobDurationBadgeProps {
  durationSeconds: number | null;
}

/** "1h04m" / "4m07s" / "12s" — the coarsest unit that still fits the value, no leading zero unit. */
function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours > 0) return `${hours}h${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m${String(secs).padStart(2, "0")}s`;
  return `${secs}s`;
}

export function JobDurationBadge({ durationSeconds }: JobDurationBadgeProps) {
  if (durationSeconds === null) return null;
  return (
    <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
      duration <span style={{ fontFamily: theme.font.mono, color: theme.color.text }}>{formatDuration(durationSeconds)}</span>
    </span>
  );
}
