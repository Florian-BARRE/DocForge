// ====== Code Summary ======
// Polls `GET /jobs/timeseries` (fleet-wide) for the trends panel — same settle-never poll shape as
// useJobsFleetPage, at a slower cadence since hourly buckets don't need sub-minute freshness.

import { useEffect, useState } from "react";
import { getJobTimeseries, type JobTimeseries } from "../../../api/jobs";

const POLL_MS = 60000;

export function useJobTimeseries(windowHours: number): { data: JobTimeseries | null; error: string | null } {
  const [data, setData] = useState<JobTimeseries | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    setData(null);

    const load = () => {
      getJobTimeseries({ windowHours })
        .then((next) => {
          if (cancelled) return;
          setData(next);
          setError(null);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => {
          if (cancelled) return;
          setError(e instanceof Error ? e.message : String(e));
          timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [windowHours]);

  return { data, error };
}
