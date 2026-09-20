// ====== Code Summary ======
// The Trace tab — the document's ingestion execution trace, reusing `DocumentProvenance` (already
// fetched for the Layout tab) rather than a second network round-trip: `GET /documents/{id}/provenance`
// resolves the latest SUCCESSFUL ingestion job for this document and folds its stage-event rows into
// `stages` (a pre-order tree walk, parent before children — identical shape/order to `GET
// /jobs/{id}/events`), so no separate `getJobTrace` call is needed here. Renders that per-node tree via
// the shared `JobEventItem` (components/trace/) — quality score, stage/kind, status ink, tokens/cost,
// input/output shape summaries and lazy full-payload buttons all come for free from that component.

import { useState } from "react";
import type { DocumentProvenance } from "../../../api/explorer";
import { Button } from "../../../components/Button";
import { EmptyState } from "../../../components/EmptyState";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { JobEventItem } from "../../../components/trace/JobEventItem";
import { theme } from "../../../theme";
import { DocumentTracePurgeDialog } from "./DocumentTracePurgeDialog";
import { useDocumentTracePurge } from "./useDocumentTracePurge";

interface TraceTabProps {
  documentId: string;
  provenance: DocumentProvenance | null;
  error: string | null;
  onRetry: () => void;
}

export function TraceTab({ documentId, provenance, error, onRetry }: TraceTabProps) {
  // Hooks before any conditional return (rules-of-hooks) — this tab needs the purge affordance
  // regardless of whether `provenance` has loaded yet.
  const [confirming, setConfirming] = useState(false);
  const { pending, error: purgeError, purge } = useDocumentTracePurge(documentId);

  const handleConfirm = async () => {
    const result = await purge();
    if (result) setConfirming(false);
  };

  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (!provenance) return <LoadingState label="loading trace…" />;

  const purgeControl = (
    <>
      <Button size="sm" variant="danger" onClick={() => setConfirming(true)}>Purge stored traces</Button>
      {confirming && (
        <DocumentTracePurgeDialog
          pending={pending}
          error={purgeError}
          onConfirm={handleConfirm}
          onCancel={() => setConfirming(false)}
        />
      )}
    </>
  );

  if (!provenance.available || provenance.stages.length === 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
        <EmptyState
          title="No trace retained for this document"
          subtitle="Either no ingestion job has completed for this document yet, or its execution trace has since been pruned/reaped. A heavy full-payload store may still exist from a prior run — purge below reclaims it either way."
        />
        <div>{purgeControl}</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.m, flexWrap: "wrap" }}>
        <span style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
          Pipeline <span style={{ fontFamily: theme.font.mono, color: theme.color.text }}>{provenance.pipeline_version}</span>
        </span>
        {provenance.job_id && (
          <span style={{ fontSize: theme.font.size.s, color: theme.color.dim }}>
            job <span style={{ fontFamily: theme.font.mono, color: theme.color.text }}>{provenance.job_id}</span>
          </span>
        )}
        <div style={{ marginLeft: "auto" }}>{purgeControl}</div>
      </div>
      <div
        style={{
          background: theme.color.surface, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, padding: `${theme.space.m}px ${theme.space.l}px`,
        }}
      >
        {provenance.stages.map((event, index) => (
          <JobEventItem key={event.event_id || index} event={event} jobId={provenance.job_id ?? ""} />
        ))}
      </div>
    </div>
  );
}
