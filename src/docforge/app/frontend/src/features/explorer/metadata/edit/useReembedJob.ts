// ====== Code Summary ======
// Polls one background job (the metadata re-embed / filterable repair enqueued by a metadata edit)
// until it reaches a terminal state. A light getJob poll — the SSE/trace machinery of the job detail
// page is overkill for a single status chip. Stops on terminal status or unmount.

import { useState } from "react";
import { getJob, type JobStatus } from "../../../../api/jobs";
import { usePolling } from "../../../../hooks/usePolling";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = ["done", "failed", "cancelled"];

export function useReembedJob(jobId: string | null): JobStatus | null {
  const [job, setJob] = useState<JobStatus | null>(null);

  // A transient fetch failure is swallowed (no `onError`) and polling continues; the chip just
  // stays on its last known state.
  usePolling(
    () => getJob(jobId as string),
    {
      intervalMs: POLL_INTERVAL_MS,
      enabled: jobId !== null,
      onReset: () => setJob(null),
      onData: setJob,
      isDone: (next) => TERMINAL_STATUSES.includes(next.status),
    },
    [jobId],
  );

  return job;
}
