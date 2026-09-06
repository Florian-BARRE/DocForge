// ====== Code Summary ======
// One worker's live activity — its id, TWO independent liveness signals (`alive` = fresh heartbeat,
// `busy` = owns a running job), and every job it currently has RUNNING. An idle-but-alive worker
// (alive:true, busy:false) is shown present, not absent; a stale-heartbeat worker (alive:false) is
// shown greyed/"offline" regardless of any job row still naming it.

import type { Navigate } from "../../shell/view";
import type { JobStatus, WorkerActivity } from "../../api/jobs";
import { theme } from "../../theme";
import { JobRow } from "./JobRow";
import { WorkerResourceReadout } from "./WorkerResourceReadout";
import { formatSince, formatUptime, liveness, LIVENESS_COLOR } from "./workerLiveness";

interface WorkerCardProps {
  activity: WorkerActivity;
  onNavigate: Navigate;
  /** Applied to the matching job in this worker's list when a cancel/stop/force call resolves. */
  onJobUpdated: (jobId: string, patch: Partial<JobStatus>) => void;
}

export function WorkerCard({ activity, onNavigate, onJobUpdated }: WorkerCardProps) {
  const state = liveness(activity);
  const color = LIVENESS_COLOR[state];

  // Capacity chip: N running against the worker's max. `max_jobs` null = unknown capacity (an old
  // heartbeat row / a worker predating this field) — show the running count with "—" for the cap,
  // never a fabricated number. A worker at/over its cap is the one "hot" signal → forge accent; a
  // worker with spare capacity is at rest → steel/muted.
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
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <strong style={{ fontFamily: theme.font.display, fontSize: theme.font.size.m, color: theme.color.text }}>
            {activity.worker_name ?? activity.worker_id}
          </strong>
          {/* An unconfigured worker's `worker_name` falls back to its own id server-side — showing
           *  both lines would just duplicate the same string, so only render the id sub-line when
           *  it's genuinely a second, distinct identifier. */}
          {activity.worker_name && activity.worker_name !== activity.worker_id && (
            <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.mute }}>
              {activity.worker_id}
            </span>
          )}
        </div>
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
      <span
        title={activity.started_at ? `registered ${new Date(activity.started_at).toLocaleString()}` : undefined}
        style={{ color: theme.color.mute, fontSize: theme.font.size.xs, fontFamily: theme.font.mono }}
      >
        last seen {formatSince(activity.last_seen)} · uptime {formatUptime(activity.started_at)}
      </span>
      <WorkerResourceReadout activity={activity} />
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
