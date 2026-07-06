// ====== Code Summary ======
// One entry of the job's per-node timeline: stage, status, duration (or the error/note the
// worker attached as `detail`).

import type { JobEvent } from "../../api/jobs";
import { theme } from "../../theme";
import { JobStatusChip } from "./JobStatusChip";

function durationLabel(event: JobEvent): string {
  if (!event.started_at || !event.finished_at) return "—";
  const ms = new Date(event.finished_at).getTime() - new Date(event.started_at).getTime();
  return `${(ms / 1000).toFixed(2)}s`;
}

export function JobEventItem({ event }: { event: JobEvent }) {
  return (
    <div
      style={{
        display: "flex", gap: theme.space.s, padding: `${theme.space.s}px 0`,
        borderLeft: `2px solid ${theme.color.line}`, paddingLeft: theme.space.m, position: "relative",
      }}
    >
      <span
        style={{
          position: "absolute", left: -5, top: theme.space.s + 2, width: 8, height: 8,
          borderRadius: 4, background: theme.color.accent,
        }}
      />
      <strong style={{ fontSize: theme.font.size.m, minWidth: 120 }}>{event.stage}</strong>
      <JobStatusChip status={event.status} />
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>{durationLabel(event)}</span>
      {event.detail && (
        <span
          style={{ color: event.status === "failed" ? theme.color.error : theme.color.dim, fontSize: theme.font.size.xs }}
        >
          {event.detail}
        </span>
      )}
    </div>
  );
}
