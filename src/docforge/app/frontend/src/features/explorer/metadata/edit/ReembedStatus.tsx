// ====== Code Summary ======
// Non-blocking feedback after a metadata save: instant "Saved", or — when the backend enqueued a
// job — a live "Re-embedding metadata…" indicator tied to it (orange while in progress, green once
// the search index caught up, red on failure) with a link to the job.

import type { MetadataUpdateResponse } from "../../../../api/documents";
import { Chip } from "../../../../components/Chip";
import type { Navigate } from "../../../../shell/view";
import { theme } from "../../../../theme";
import { useReembedJob } from "./useReembedJob";

interface ReembedStatusProps {
  result: MetadataUpdateResponse;
  collectionId: string;
  onNavigate: Navigate;
}

export function ReembedStatus({ result, collectionId, onNavigate }: ReembedStatusProps) {
  const jobId = result.job_id ?? null;
  const job = useReembedJob(jobId);
  const status = job?.status ?? "pending";
  const terminal = job !== null && ["done", "failed", "cancelled"].includes(status);

  let chip: JSX.Element;
  if (!jobId) chip = <Chip tone="ok">Saved</Chip>;
  else if (status === "done") chip = <Chip tone="ok">{result.reembedding ? "Saved · search index updated" : "Saved · index synced"}</Chip>;
  else if (status === "failed" || status === "cancelled")
    chip = <Chip tone="error" title={job?.error ?? undefined}>{`Saved · background update ${status}`}</Chip>;
  else chip = <Chip tone="accent">{result.reembedding ? "Saved · re-embedding metadata…" : "Saved · syncing search filters…"}</Chip>;

  return (
    <div role="status" style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap", fontSize: theme.font.size.s }}>
      {chip}
      {jobId && !terminal && result.reembedding && (
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>
          Search results for {result.reembed_fields.join(", ")} update once this finishes.
        </span>
      )}
      {jobId && (
        <button
          type="button"
          onClick={() => onNavigate({ name: "job", collectionId, jobId })}
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: theme.color.accentSafe, fontSize: theme.font.size.xs, textDecoration: "underline" }}
        >
          View job
        </button>
      )}
    </div>
  );
}
