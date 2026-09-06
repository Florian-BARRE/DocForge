// ====== Code Summary ======
// Fetches one bounded page of the FLEET-WIDE job list (`listJobsPage` with no `collectionId`) for
// the given status/order/pagination, polling continuously while mounted — mirrors WorkersPanel's
// "always-live fleet monitor" pattern rather than JobsPage's settle-and-stop poll, since the fleet
// view has no notion of a settled batch (jobs keep arriving from every collection).

import { useEffect, useState } from "react";
import { listJobsPage, type JobOrder, type JobPage, type JobStatus, type JobStatusValue } from "../../../api/jobs";

const POLL_MS = 4000;

interface UseJobsFleetPageArgs {
  status?: JobStatusValue[];
  order: JobOrder;
  limit: number;
  offset: number;
}

interface UseJobsFleetPageResult {
  page: JobPage | null;
  error: string | null;
  patchJob: (jobId: string, patch: Partial<JobStatus>) => void;
}

export function useJobsFleetPage({ status, order, limit, offset }: UseJobsFleetPageArgs): UseJobsFleetPageResult {
  const [page, setPage] = useState<JobPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    // A tab/page change must show its OWN loading state, not the previous page's stale rows.
    setPage(null);

    const load = () => {
      listJobsPage({ status, order, limit, offset })
        .then((data) => {
          if (cancelled) return;
          setPage(data);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `status` is a fresh array each render; join it into a stable key instead.
  }, [status?.join(","), order, limit, offset]);

  const patchJob = (jobId: string, patch: Partial<JobStatus>) => {
    setPage((prev) =>
      prev ? { ...prev, jobs: prev.jobs.map((j) => (j.job_id === jobId ? { ...j, ...patch } : j)) } : prev,
    );
  };

  return { page, error, patchJob };
}
