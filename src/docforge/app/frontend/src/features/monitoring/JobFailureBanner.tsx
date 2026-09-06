// ====== Code Summary ======
// The job detail page's prominent "why it failed" block — promoted out of JobSummaryCard's small
// footer text into a header-level banner once a job has FAILED (never shown for cancelled — that's
// a deliberate stop, not a failure, per FailedNodeBreadcrumb's own convention). Leads with the flat
// error message (always present on a failed job) and the attempt count, then layers the structured
// breadcrumb (failed node/kind/item, current stage, error_type) when the worker recorded one — the
// breadcrumb component itself falls back to rendering nothing on jobs from before those columns
// existed (failed_node_id null), leaving just the flat message.

import type { JobStatus } from "../../api/jobs";
import { theme } from "../../theme";
import { FailedNodeBreadcrumb } from "./FailedNodeBreadcrumb";

interface JobFailureBannerProps {
  job: JobStatus;
}

export function JobFailureBanner({ job }: JobFailureBannerProps) {
  if (job.status !== "failed") return null;

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.xs,
        background: theme.color.errorSoft, border: `1px solid ${theme.color.error}`,
        borderRadius: theme.radius.l, padding: theme.space.l, marginBottom: theme.space.l,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s }}>
        <span
          style={{
            fontFamily: theme.font.display, fontWeight: theme.font.weight.bold,
            fontSize: theme.font.size.l, color: theme.color.errorStrong,
          }}
        >
          Job failed
        </span>
        <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute }}>attempt {job.attempt}</span>
      </div>
      <FailedNodeBreadcrumb job={job} />
      {job.error && <div style={{ color: theme.color.text, fontSize: theme.font.size.s }}>{job.error}</div>}
    </div>
  );
}
