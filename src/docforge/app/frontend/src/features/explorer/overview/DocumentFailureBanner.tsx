// ====== Code Summary ======
// The document Summary tab's "why it didn't make it" block — mirrors JobFailureBanner's layout but
// at document scope (a document keeps its own failure_reason even after a later successful
// re-ingest job, so it cannot just re-render the job banner). Shown for `failed` (error tone) and
// `cancelled` (skip tone — a deliberate stop, never the error red, per brand.md) documents; renders
// nothing otherwise. Links to the collection's Jobs tab since a document doesn't carry its job id.

import { humanizeJobError } from "../../monitoring/jobErrorHumanize";
import type { DocumentDetail } from "../../../api/explorer";
import type { Navigate } from "../../../shell/view";
import { theme } from "../../../theme";

interface DocumentFailureBannerProps {
  document: DocumentDetail;
  collectionId: string;
  onNavigate: Navigate;
}

export function DocumentFailureBanner({ document, collectionId, onNavigate }: DocumentFailureBannerProps) {
  if (document.status !== "failed" && document.status !== "cancelled") return null;

  const isFailed = document.status === "failed";
  const tone = isFailed
    ? { bg: theme.color.errorSoft, border: theme.color.error, strong: theme.color.errorStrong }
    : { bg: theme.color.skipSoft, border: theme.color.skip, strong: theme.color.skipStrong };
  const message = document.failure_reason
    ? humanizeJobError(document.failure_reason)
    : isFailed
      ? "Ingestion failed — no further detail was recorded."
      : "Ingestion was cancelled before it completed.";

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.xs,
        background: tone.bg, border: `1px ${isFailed ? "solid" : "dashed"} ${tone.border}`,
        borderRadius: theme.radius.l, padding: theme.space.l,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s }}>
        <span
          style={{
            fontFamily: theme.font.display, fontWeight: theme.font.weight.bold,
            fontSize: theme.font.size.l, color: tone.strong,
          }}
        >
          {isFailed ? "Ingestion failed" : "Ingestion cancelled"}
        </span>
        <button
          onClick={() => onNavigate({ name: "collection-jobs", collectionId })}
          style={{
            background: "none", border: `1px solid ${tone.border}`, color: tone.strong,
            borderRadius: theme.radius.s, padding: "4px 10px", fontSize: theme.font.size.xs, cursor: "pointer",
          }}
        >
          View jobs
        </button>
      </div>
      <div style={{ color: theme.color.text, fontSize: theme.font.size.s }}>{message}</div>
    </div>
  );
}
