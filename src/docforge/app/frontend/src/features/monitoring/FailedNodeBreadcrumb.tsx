// ====== Code Summary ======
// Structured "where it died" summary for a failed job — built from the worker's failure breadcrumb
// fields (failed_node_id/kind, failed_item_index, error_type) instead of parsing the flat `error`
// string. Renders nothing when the job hasn't failed or the worker predates the breadcrumb columns
// (failed_node_id null) — the caller keeps the flat message visible as a fallback in that case.

import type { JobStatus } from "../../api/jobs";
import { theme } from "../../theme";

interface FailedNodeBreadcrumbProps {
  job: JobStatus;
}

export function FailedNodeBreadcrumb({ job }: FailedNodeBreadcrumbProps) {
  if (job.status !== "failed" || !job.failed_node_id) return null;

  const stage = job.current_stage ?? "unknown stage";
  const itemLabel =
    job.failed_item_index !== null
      ? `item ${job.failed_item_index}${job.items_total !== null ? `/${job.items_total}` : ""}`
      : null;

  return (
    <div
      style={{
        display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.xs,
        color: theme.color.error, fontSize: theme.font.size.s, fontWeight: theme.font.weight.medium,
      }}
    >
      <span>failed at</span>
      <span style={{ fontFamily: theme.font.mono }}>{stage}</span>
      {itemLabel && <span style={{ fontFamily: theme.font.mono }}>{itemLabel}</span>}
      <span>· node</span>
      <span style={{ fontFamily: theme.font.mono }}>{job.failed_node_id}</span>
      {job.failed_node_kind && (
        <span style={{ fontFamily: theme.font.mono, color: theme.color.mute }}>({job.failed_node_kind})</span>
      )}
      {job.error_type && (
        <>
          <span>·</span>
          <span style={{ fontFamily: theme.font.mono, fontWeight: theme.font.weight.bold }}>{job.error_type}</span>
        </>
      )}
    </div>
  );
}
