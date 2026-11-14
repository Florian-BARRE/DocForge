// ====== Code Summary ======
// Builds a job_id -> worker label lookup from the live worker feed (`GET /jobs/workers/live`), so
// the fleet-wide Running tab can show WHO is running a job — the only place that information exists
// (a job's own JobStatus row carries no worker_id; only a worker's live activity snapshot names its
// currently-running jobs). Polls continuously, independent of the jobs-page poll.

import { useState } from "react";
import { getWorkersLive } from "../../../api/jobs";
import { usePolling } from "../../../hooks/usePolling";

const POLL_MS = 4000;

export function useRunningWorkerMap(): Record<string, string> {
  const [map, setMap] = useState<Record<string, string>>({});

  // Failures stay silent — an unresolved probe just leaves the Running tab's worker column showing
  // "—" rather than surfacing a second error banner on top of the jobs-page one.
  usePolling(
    () => getWorkersLive(),
    {
      intervalMs: POLL_MS,
      onData: ({ workers }) => {
        const next: Record<string, string> = {};
        for (const worker of workers) {
          const label = worker.worker_name ?? worker.worker_id;
          for (const job of worker.jobs) next[job.job_id] = label;
        }
        setMap(next);
      },
    },
    [],
  );

  return map;
}
