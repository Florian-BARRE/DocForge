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
        background: theme.color.panel, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: theme.space.m,
        display: "flex", flexDirection: "column", gap: theme.space.s,
      }}
    >
      <strong style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.m }}>{activity.worker_id}</strong>
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
