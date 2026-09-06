// ====== Code Summary ======
// One worker's live resource card for the Monitoring dashboard — liveness, capacity, uptime and
// running-job count alongside the CPU/memory readout. Deliberately does NOT list the worker's
// individual job rows (that detail already lives on the Workers page / recent-jobs panel below) —
// this card is the "how hard is this worker working, right now" surface.

import type { WorkerActivity } from "../../api/jobs";
import { theme } from "../../theme";
import { WorkerResourceReadout } from "./WorkerResourceReadout";
import { formatSince, formatUptime, liveness, LIVENESS_COLOR } from "./workerLiveness";

export function WorkerLiveCard({ activity }: { activity: WorkerActivity }) {
  const state = liveness(activity);
  const color = LIVENESS_COLOR[state];

  const running = activity.jobs.length;
  const capacityLabel = activity.max_jobs === null ? `${running} / —` : `${running} / ${activity.max_jobs}`;
  const atCapacity = activity.max_jobs !== null && running >= activity.max_jobs;

  return (
    <div
      style={{
        background: theme.color.surface, border: `1px ${state === "offline" ? "dashed" : "solid"} ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
        display: "flex", flexDirection: "column", gap: theme.space.s,
        opacity: state === "offline" ? 0.65 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ width: 8, height: 8, borderRadius: theme.radius.pill, background: color, flexShrink: 0 }} />
        <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.m, color: theme.color.text, minWidth: 0 }}>
          {activity.worker_name ?? activity.worker_id}
        </strong>
        <span
          title="running jobs / configured capacity"
          style={{
            marginLeft: "auto", fontFamily: theme.font.mono, fontSize: theme.font.size.xs,
            padding: `2px ${theme.space.s}px`, borderRadius: theme.radius.pill,
            background: atCapacity ? theme.color.accentSoft : theme.color.surface2,
            border: `1px solid ${atCapacity ? theme.color.accentLine : theme.color.line}`,
            color: atCapacity ? theme.color.accentSafe : theme.color.mute,
          }}
        >
          {capacityLabel}
        </span>
        <span
          style={{
            color, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
            textTransform: "uppercase", letterSpacing: "0.04em",
          }}
        >
          {state}
        </span>
      </div>
      <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}>
        last seen {formatSince(activity.last_seen)} · uptime {formatUptime(activity.started_at)}
      </span>
      <WorkerResourceReadout activity={activity} />
    </div>
  );
}
