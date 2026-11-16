// ====== Code Summary ======
// A titled, polled panel of recent fleet-wide jobs matching a status filter — the shared backfill
// content for the Workers page ("Recent activity across the fleet") and the Monitoring page
// ("Recent completed jobs"), so both read as a living view instead of stopping at a handful of
// summary numbers in an otherwise empty canvas.

import { useState } from "react";
import { listJobsPage, type JobStatus, type JobStatusValue } from "../../api/jobs";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { JobRow } from "./JobRow";
import { errorMessage } from "../../hooks/errorMessage";
import { usePolling } from "../../hooks/usePolling";

const POLL_MS = 5000;

interface RecentJobsPanelProps {
  title: string;
  status: JobStatusValue[];
  limit?: number;
  emptyLabel: string;
  onNavigate: Navigate;
}

export function RecentJobsPanel({ title, status, limit = 8, emptyLabel, onNavigate }: RecentJobsPanelProps) {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // `status` is a fresh array literal from the caller on every render — compare by content
  // (JSON.stringify), not identity, so this loop doesn't re-poll/flicker on every parent render.
  usePolling(
    () => listJobsPage({ status, order: "newest", limit }),
    {
      intervalMs: POLL_MS,
      onData: (page) => { setJobs(page.jobs); setError(null); },
      onError: (e) => setError(errorMessage(e)),
    },
    [JSON.stringify(status), limit],
  );

  return (
    <div>
      <div
        style={{
          fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.xl,
          color: theme.color.text, marginBottom: theme.space.m,
        }}
      >
        {title}
      </div>
      {error && <ErrorState message={error} />}
      {!error && !jobs && <LoadingState label="loading…" />}
      {!error && jobs && jobs.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>{emptyLabel}</div>
      )}
      {!error && jobs && jobs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          {jobs.map((job) => (
            <JobRow
              key={job.job_id}
              job={job}
              onClick={() => onNavigate({ name: "job", collectionId: job.collection_id, jobId: job.job_id })}
              onUpdated={(patch) =>
                setJobs((prev) => (prev ? prev.map((j) => (j.job_id === job.job_id ? { ...j, ...patch } : j)) : prev))
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
