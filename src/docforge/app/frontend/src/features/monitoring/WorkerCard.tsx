// ====== Code Summary ======
// One worker's live activity — its id, TWO independent liveness signals (`alive` = fresh heartbeat,
// `busy` = owns a running job), and every job it currently has RUNNING. An idle-but-alive worker
// (alive:true, busy:false) is shown present, not absent; a stale-heartbeat worker (alive:false) is
// shown greyed/"offline" regardless of any job row still naming it.

import type { Navigate } from "../../shell/view";
import type { JobStatus, WorkerActivity } from "../../api/jobs";
import { theme } from "../../theme";
import { JobRow } from "./JobRow";

interface WorkerCardProps {
  activity: WorkerActivity;
  onNavigate: Navigate;
  /** Applied to the matching job in this worker's list when a cancel/stop/force call resolves. */
  onJobUpdated: (jobId: string, patch: Partial<JobStatus>) => void;
}

type Liveness = "busy" | "idle" | "offline";

function liveness(activity: WorkerActivity): Liveness {
  if (!activity.alive) return "offline";
  return activity.busy ? "busy" : "idle";
}

// Busy = the one thing being worked → forge orange. Idle-alive = present but at rest → neutral
// steel (never green — green is reserved for "done"). Offline = absent → muted warm grey.
const COLOR_BY_LIVENESS: Record<Liveness, string> = {
  busy: theme.color.accent,
  idle: theme.color.info,
  offline: theme.color.mute,
};

function formatSince(value: string | null): string {
  if (!value) return "no heartbeat recorded";
  const seconds = Math.floor((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  return `${Math.floor(seconds / 60)}m ago`;
}

export function WorkerCard({ activity, onNavigate, onJobUpdated }: WorkerCardProps) {
  const state = liveness(activity);
  const color = COLOR_BY_LIVENESS[state];

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
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.m, color: theme.color.text }}>
            {activity.worker_name ?? activity.worker_id}
          </strong>
          {activity.worker_name && (
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
              {activity.worker_id}
            </span>
          )}
        </div>
        <span
          style={{
            marginLeft: "auto", color, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
            textTransform: "uppercase", letterSpacing: "0.04em",
          }}
        >
          {state}
        </span>
      </div>
      <span
        title={activity.started_at ? `registered ${new Date(activity.started_at).toLocaleString()}` : undefined}
        style={{ color: theme.color.mute, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}
      >
        last seen {formatSince(activity.last_seen)}
      </span>
      {activity.jobs.length === 0 && (
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          {state === "offline" ? "no recent heartbeat" : "no running job"}
        </span>
      )}
      {activity.jobs.map((job) => (
        <JobRow
          key={job.job_id}
          job={job}
          onClick={() => onNavigate({ name: "job", collectionId: job.collection_id, jobId: job.job_id })}
          onUpdated={(patch) => onJobUpdated(job.job_id, patch)}
        />
      ))}
    </div>
  );
}
