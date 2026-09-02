// ====== Code Summary ======
// The human-readable anchor for a job row: the document filename leads (Archivo, the name a user
// actually recognizes), with the collection name, current stage, and both ids (job/document) as
// secondary mono metadata underneath — ids stay visible, just demoted. Reused by JobRow (so both
// JobsPage and WorkerCard get it) and JobDetailPage's header.

import { jobDisplayName, type JobStatus } from "../../api/jobs";
import { theme } from "../../theme";

export function JobIdentity({ job }: { job: JobStatus }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <span
        title={job.document_filename ?? undefined}
        style={{
          fontFamily: theme.font.display, fontWeight: theme.font.weight.semibold, fontSize: theme.font.size.l,
          color: theme.color.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 420,
        }}
      >
        {jobDisplayName(job)}
      </span>
      <span
        style={{
          display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.xs,
          color: theme.color.mute, fontSize: theme.font.size.xs,
        }}
      >
        {job.collection_name && <span style={{ color: theme.color.dim }}>{job.collection_name}</span>}
        {job.current_stage && <span>stage {job.current_stage}</span>}
        <span style={{ fontFamily: theme.font.mono }}>job {job.job_id.slice(0, 8)}</span>
        <span style={{ fontFamily: theme.font.mono }}>doc {job.document_id.slice(0, 8)}</span>
      </span>
    </div>
  );
}
