// ====== Code Summary ======
// Renders one page of fleet-wide jobs as JobRow cards, each carrying the worker-attribution footer
// (pending: honest "—", running: the live worker join, done/failed/all: nothing — see
// WorkerAttributionLine). A row click opens the job's own detail page.

import type { JobStatus } from "../../api/jobs";
import { InlineErrorBoundary } from "../../components/InlineErrorBoundary";
import { JobRow } from "../monitoring/JobRow";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { WorkerAttributionLine } from "./WorkerAttributionLine";

interface JobFleetListProps {
  jobs: JobStatus[];
  workerMap: Record<string, string>;
  onNavigate: Navigate;
  onJobUpdated: (jobId: string, patch: Partial<JobStatus>) => void;
}

export function JobFleetList({ jobs, workerMap, onNavigate, onJobUpdated }: JobFleetListProps) {
  return (
    <InlineErrorBoundary label="the job list">
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
        {jobs.map((job) => (
          <JobRow
            key={job.job_id}
            job={job}
            onClick={() => onNavigate({ name: "job", collectionId: job.collection_id, jobId: job.job_id })}
            onUpdated={(patch) => onJobUpdated(job.job_id, patch)}
            footer={<WorkerAttributionLine job={job} workerLabel={workerMap[job.job_id]} />}
          />
        ))}
      </div>
    </InlineErrorBoundary>
  );
}
