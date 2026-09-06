// ====== Code Summary ======
// Home's "recent failures" strip — the last 5 failed jobs fleet-wide, each a JobRow (reused as-is,
// no worker footer here — that's an All-Jobs-only concern) that opens straight into the job's own
// detail page. Self-contained fetch+poll so a failure elsewhere on Home never blocks this section.

import { useEffect, useState } from "react";
import { listJobsPage, type JobStatus } from "../../api/jobs";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { InlineErrorBoundary } from "../../components/InlineErrorBoundary";
import { LoadingState } from "../../components/LoadingState";
import { JobRow } from "../monitoring/JobRow";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";

const POLL_MS = 8000;
const RECENT_FAILURES_LIMIT = 5;

interface RecentFailuresStripProps {
  onNavigate: Navigate;
}

export function RecentFailuresStrip({ onNavigate }: RecentFailuresStripProps) {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      listJobsPage({ status: ["failed"], order: "newest", limit: RECENT_FAILURES_LIMIT })
        .then((page) => {
          if (cancelled) return;
          setJobs(page.jobs);
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
  }, []);

  return (
    <div>
      <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.l, fontWeight: 600, color: theme.color.text, marginBottom: theme.space.m }}>
        Recent failures
      </h2>
      {error && <ErrorState message={error} />}
      {!error && !jobs && <LoadingState label="loading recent failures…" />}
      {!error && jobs && jobs.length === 0 && (
        <EmptyState icon="✓" title="No recent failures" subtitle="The fleet has had a clean run lately." />
      )}
      {!error && jobs && jobs.length > 0 && (
        <InlineErrorBoundary label="the recent-failures strip">
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
        </InlineErrorBoundary>
      )}
    </div>
  );
}
