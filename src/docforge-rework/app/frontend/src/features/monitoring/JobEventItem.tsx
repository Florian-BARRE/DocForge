// ====== Code Summary ======
// One entry of the job's per-node timeline: stage, status, duration (or the error/note the
// worker attached as `detail`). Each item carries its own left rail segment + a status-colored
// node marker, so stacking them (JobDetailPage) reads as one continuous vertical timeline.

import type { JobEvent } from "../../api/jobs";
import { theme } from "../../theme";
import { JobStatusChip } from "./JobStatusChip";

const NODE_COLOR_BY_STATUS: Record<string, string> = {
  running: theme.color.accent,
  done: theme.color.ok,
  success: theme.color.ok,
  failed: theme.color.error,
  error: theme.color.error,
  skipped: theme.color.mute,
};

function durationLabel(event: JobEvent): string {
  if (!event.started_at || !event.finished_at) return "—";
  const ms = new Date(event.finished_at).getTime() - new Date(event.started_at).getTime();
  return `${(ms / 1000).toFixed(2)}s`;
}

export function JobEventItem({ event }: { event: JobEvent }) {
  const nodeColor = NODE_COLOR_BY_STATUS[event.status] ?? theme.color.dim;
  return (
    <div
      style={{
        display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.s,
        padding: `${theme.space.s}px 0`, borderLeft: `2px solid ${theme.color.line}`,
        paddingLeft: theme.space.m, position: "relative",
      }}
    >
      <span
        style={{
          position: "absolute", left: -6, top: theme.space.s + 4, width: 10, height: 10,
          borderRadius: theme.radius.pill, background: nodeColor,
          boxShadow: `0 0 0 3px ${theme.color.bg}`,
        }}
      />
      <strong style={{ fontSize: theme.font.size.m, color: theme.color.text, minWidth: 140 }}>{event.stage}</strong>
      <JobStatusChip status={event.status} />
      <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}>{durationLabel(event)}</span>
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
