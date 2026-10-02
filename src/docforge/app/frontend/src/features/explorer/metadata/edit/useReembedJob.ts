// ====== Code Summary ======
// Polls one background job (the metadata re-embed / filterable repair enqueued by a metadata edit)
// until it reaches a terminal state. A light getJob poll — the SSE/trace machinery of the job detail
// page is overkill for a single status chip. Stops on terminal status or unmount.

import { useEffect, useState } from "react";
import { getJob, type JobStatus } from "../../../../api/jobs";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = ["done", "failed", "cancelled"];

export function useReembedJob(jobId: string | null): JobStatus | null {
  const [job, setJob] = useState<JobStatus | null>(null);

  useEffect(() => {
    setJob(null);
    if (!jobId) return undefined;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = () => {
      getJob(jobId)
        .then((next) => {
          if (cancelled) return;
          setJob(next);
          if (!TERMINAL_STATUSES.includes(next.status)) timer = setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch(() => {
          // Transient fetch failure — keep polling; the chip just stays on its last known state.
          if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS);
        });
    };
    poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return job;
}
