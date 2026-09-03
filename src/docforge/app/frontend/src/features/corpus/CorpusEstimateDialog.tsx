// ====== Code Summary ======
// The corpus toolbar's "Estimate cost" result — a modal (same overlay shape as BulkConfirmDialog)
// that runs the dry-run estimate for the current selection/filter on open and renders it with the
// SAME presentational pieces the collection Overview's cost panel uses (Headline/StageTable/
// Caveats). A deliberate cross-feature import, not a duplicate: those three are pure `estimate in,
// JSX out` components with zero corpus-specific coupling, and this dialog is the one place besides
// the Overview panel that needs the exact same rendering of a `CostEstimate` — see
// agent-memory/frontend for the precedent (AdvancedDisclosure/formatBytes already cross-imported
// into features/collections/storage the same way).

import { useEffect, useState } from "react";
import { estimateCollectionCost, type CostEstimate, type EstimateSubset } from "../../api/collections";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { CostEstimateCaveats } from "../collections/estimate/CostEstimateCaveats";
import { CostEstimateHeadline } from "../collections/estimate/CostEstimateHeadline";
import { CostEstimateStageTable } from "../collections/estimate/CostEstimateStageTable";
import { useFocusTrap } from "../../shell/useFocusTrap";
import { theme } from "../../theme";

interface CorpusEstimateDialogProps {
  collectionId: string;
  subset: EstimateSubset;
  /** A short human phrase naming what is covered — e.g. "12 selected documents" or "the 340
   *  documents matching the current filters". Shown as the dialog's subtitle. */
  subjectLabel: string;
  onClose: () => void;
}

export function CorpusEstimateDialog({ collectionId, subset, subjectLabel, onClose }: CorpusEstimateDialogProps) {
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const panelRef = useFocusTrap<HTMLDivElement>(onClose);

  const run = () => {
    setLoading(true);
    setError(null);
    estimateCollectionCost(collectionId, "pending", subset)
      .then(setEstimate)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  // Keyed on a stringified subset (mirrors CorpusPage's own filter-dependency convention) — the
  // dialog is opened with a freshly-built `subset` object every render otherwise, which would
  // re-trigger the fetch in a loop if compared by reference instead of value.
  useEffect(run, [collectionId, JSON.stringify(subset)]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Cost estimate"
        tabIndex={-1}
        style={{
          background: theme.color.panel, border: `1px solid ${theme.color.accentLine}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 640, width: "100%", maxHeight: "85vh", overflowY: "auto",
          display: "flex", flexDirection: "column", gap: theme.space.l,
        }}
      >
        <div>
          <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
            Cost estimate
          </h2>
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginTop: 4 }}>Projected for {subjectLabel} — read-only, no ingestion is triggered.</div>
        </div>

        {error && <ErrorState message={error} onRetry={run} />}
        {!error && loading && <LoadingState label="running dry-run estimate…" />}
        {!error && !loading && estimate && (
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xl }}>
            <CostEstimateHeadline estimate={estimate} />
            <CostEstimateStageTable stages={estimate.stages} />
            <CostEstimateCaveats estimate={estimate} />
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}
