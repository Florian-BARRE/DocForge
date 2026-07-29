// ====== Code Summary ======
// One worker's live activity — its id + every job it currently has RUNNING.

import type { WorkerActivity } from "../../api/jobs";
import { theme } from "../../theme";
import type { Navigate } from "../../shell/view";
import { JobRow } from "./JobRow";

interface WorkerCardProps {
  activity: WorkerActivity;
  onNavigate: Navigate;
}

export function WorkerCard({ activity, onNavigate }: WorkerCardProps) {
  return (
    <div
      style={{
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: theme.space.l,
        display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span
          style={{
            width: 8, height: 8, borderRadius: theme.radius.pill,
            background: activity.jobs.length > 0 ? theme.color.ok : theme.color.mute,
          }}
        />
        <strong style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.m, color: theme.color.text }}>{activity.worker_id}</strong>
      </div>
      {activity.jobs.length === 0 && (
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>no running job</span>
      )}
      {activity.jobs.map((job) => (
        <JobRow
          key={job.job_id}
          job={job}
          onClick={() => onNavigate({ name: "job", collectionId: job.collection_id, jobId: job.job_id })}
        />
      ))}
    </div>
  );
}
