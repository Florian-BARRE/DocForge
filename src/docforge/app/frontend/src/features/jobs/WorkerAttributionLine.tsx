// ====== Code Summary ======
// The fleet-wide All Jobs view's "who is running this" line, rendered as a JobRow footer. A
// pending job NEVER shows a fabricated worker (arq only assigns one at claim time — see
// api/jobs.ts's JobStatus docstring); a running job shows the real label from the live worker feed,
// or an honest "—" if the join hasn't resolved yet. Done/failed/cancelled jobs render nothing: the
// current JobStatus contract carries no historical worker_id (see AGENT report — a backend gap, not
// something this UI may invent a value for).

import type { JobStatus } from "../../api/jobs";
import { theme } from "../../theme";

interface WorkerAttributionLineProps {
  job: JobStatus;
  /** This job's live worker label, from useRunningWorkerMap — undefined/absent means unresolved. */
  workerLabel: string | undefined;
}

export function WorkerAttributionLine({ job, workerLabel }: WorkerAttributionLineProps) {
  if (job.status === "pending") {
    return (
      <div
        title="arq assigns a worker only once it claims the job off the queue"
        style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}
      >
        worker — <span style={{ fontStyle: "italic" }}>(assigned at claim time)</span>
      </div>
    );
  }

  if (job.status === "running") {
    return (
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
        worker <span style={{ fontFamily: theme.font.mono, color: theme.color.text }}>{workerLabel ?? "—"}</span>
      </div>
    );
  }

  return null;
}
