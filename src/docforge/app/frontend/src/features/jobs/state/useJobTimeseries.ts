// ====== Code Summary ======
// Polls `GET /jobs/timeseries` (fleet-wide) for the trends panel — same settle-never poll shape as
// useJobsFleetPage, at a slower cadence since hourly buckets don't need sub-minute freshness.

import { useState } from "react";
import { getJobTimeseries, type JobTimeseries } from "../../../api/jobs";
import { errorMessage } from "../../../hooks/errorMessage";
import { usePolling } from "../../../hooks/usePolling";

const POLL_MS = 60000;

export function useJobTimeseries(windowHours: number): { data: JobTimeseries | null; error: string | null } {
  const [data, setData] = useState<JobTimeseries | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePolling(
    () => getJobTimeseries({ windowHours }),
    {
      intervalMs: POLL_MS,
      onReset: () => setData(null),
      onData: (next) => { setData(next); setError(null); },
      onError: (e) => setError(errorMessage(e)),
    },
    [windowHours],
  );

  return { data, error };
}
