// ====== Code Summary ======
// Fetches one bounded page of the FLEET-WIDE job list (`listJobsPage` with no `collectionId`) for
// the given status/order/pagination, polling continuously while mounted — mirrors WorkersPanel's
// "always-live fleet monitor" pattern rather than JobsPage's settle-and-stop poll, since the fleet
// view has no notion of a settled batch (jobs keep arriving from every collection).

import { useState } from "react";
import { listJobsPage, type JobOrder, type JobPage, type JobSort, type JobStatus, type JobStatusValue } from "../../../api/jobs";
import { errorMessage } from "../../../hooks/errorMessage";
import { usePolling } from "../../../hooks/usePolling";

const POLL_MS = 4000;

interface UseJobsFleetPageArgs {
  status?: JobStatusValue[];
  order: JobOrder;
  sort?: JobSort;
  limit: number;
  offset: number;
  collectionId?: string;
  stage?: string;
  errorType?: string;
  search?: string;
  createdAfter?: string;
  createdBefore?: string;
}

interface UseJobsFleetPageResult {
  page: JobPage | null;
  error: string | null;
  patchJob: (jobId: string, patch: Partial<JobStatus>) => void;
}

export function useJobsFleetPage({
  status, order, sort, limit, offset, collectionId, stage, errorType, search, createdAfter, createdBefore,
}: UseJobsFleetPageArgs): UseJobsFleetPageResult {
  const [page, setPage] = useState<JobPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  usePolling(
    () => listJobsPage({ status, order, sort, limit, offset, collectionId, stage, errorType, search, createdAfter, createdBefore }),
    {
      intervalMs: POLL_MS,
      // A tab/page/filter change must show its OWN loading state, not the previous page's stale rows.
      onReset: () => setPage(null),
      onData: (data) => { setPage(data); setError(null); },
      onError: (e) => setError(errorMessage(e)),
    },
    // `status` is a fresh array each render; join it into a stable key instead.
    [status?.join(","), order, sort, limit, offset, collectionId, stage, errorType, search, createdAfter, createdBefore],
  );

  const patchJob = (jobId: string, patch: Partial<JobStatus>) => {
    setPage((prev) =>
      prev ? { ...prev, jobs: prev.jobs.map((j) => (j.job_id === jobId ? { ...j, ...patch } : j)) } : prev,
    );
  };

  return { page, error, patchJob };
}
