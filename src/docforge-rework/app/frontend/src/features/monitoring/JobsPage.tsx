// ====== Code Summary ======
// A collection's jobs, newest first (the backend already orders them) — polls every 2.5s while
// any job is still pending or running, stops once the batch has settled.

import { useEffect, useState } from "react";
import { listJobs, type JobStatus } from "../../api/jobs";
import { BackLink } from "../../components/BackLink";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { JobRow } from "./JobRow";

const POLL_MS = 2500;

interface JobsPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

function isActive(job: JobStatus): boolean {
  return job.status === "pending" || job.status === "running";
}

export function JobsPage({ collectionId, onNavigate }: JobsPageProps) {
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      listJobs(collectionId)
        .then((data) => {
          if (cancelled) return;
          setJobs(data);
          setError(null);
          if (data.some(isActive)) timer = window.setTimeout(load, POLL_MS);
        })
        .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [collectionId]);

  return (
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <BackLink label="Collection" onClick={() => onNavigate({ name: "collection", collectionId })} />
      <h1 style={{ fontSize: theme.font.size.xl, margin: `${theme.space.s}px 0 ${theme.space.l}px` }}>Jobs</h1>
      {error && <ErrorState message={error} />}
      {!error && !jobs && <LoadingState label="loading jobs…" />}
      {jobs && jobs.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No jobs yet — upload a document to see one here.</div>
      )}
      {jobs && jobs.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          {jobs.map((job) => (
            <JobRow key={job.job_id} job={job} onClick={() => onNavigate({ name: "job", collectionId, jobId: job.job_id })} />
          ))}
        </div>
      )}
    </div>
  );
}
