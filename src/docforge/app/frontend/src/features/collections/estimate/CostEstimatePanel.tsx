// ====== Code Summary ======
// The collection Overview's "Cost estimate" card — sits beside StorageFootprintPanel but is
// explicitly user-triggered rather than self-fetched on mount: a dry-run sweep is heavier than a
// glance-worthy stat, and an auto-fetched estimate could go stale silently. Pick a scope
// (pending-only vs the whole collection), click "Estimate cost", and the panel renders the
// projected spend + volume of ingesting — read-only, triggers no job.

import { useState } from "react";
import { estimateCollectionCost, type CostEstimate, type EstimateScope } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { TabNav } from "../../../components/TabNav";
import { theme as t } from "../../../theme";
import { CostEstimateCaveats } from "./CostEstimateCaveats";
import { CostEstimateHeadline } from "./CostEstimateHeadline";
import { CostEstimateStageTable } from "./CostEstimateStageTable";

interface CostEstimatePanelProps {
  collectionId: string;
}

const SCOPE_TABS: { key: EstimateScope; label: string }[] = [
  { key: "pending", label: "Pending only" },
  { key: "all", label: "Whole collection" },
];

export function CostEstimatePanel({ collectionId }: CostEstimatePanelProps) {
  const [scope, setScope] = useState<EstimateScope>("pending");
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = () => {
    setLoading(true);
    setError(null);
    estimateCollectionCost(collectionId, scope)
      .then(setEstimate)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, marginBottom: t.space.l, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m, padding: `${t.space.m}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}`, flexWrap: "wrap" }}>
        <span style={{ fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xl, color: t.color.text }}>
          Cost estimate
        </span>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: t.space.m, flexWrap: "wrap" }}>
          <TabNav
            tabs={SCOPE_TABS}
            active={scope}
            onSelect={setScope}
            navId="cost-estimate-scope"
            ariaLabel="Estimate scope"
            role="group"
          />
          {/* Steel, not orange — this is a routine, repeatable dry-run action, not the Overview's
              one primary thing (that's the Upload hero); brand.md reserves forge orange for a
              single accent per screen. */}
          <Button size="sm" variant="secondary" onClick={run} disabled={loading}>
            {loading ? "Estimating…" : estimate ? "Re-estimate" : "Estimate cost"}
          </Button>
        </div>
      </div>

      <div style={{ padding: t.space.l }}>
        {error && <ErrorState message={error} onRetry={run} />}
        {!error && loading && <LoadingState label="running dry-run estimate…" />}
        {!error && !loading && !estimate && (
          <div style={{ color: t.color.dim, fontSize: t.font.size.m, textAlign: "center", padding: t.space.xl }}>
            Preview the projected cost and volume of ingesting this collection before committing — read-only, no ingestion is triggered.
          </div>
        )}
        {!error && !loading && estimate && (
          <div style={{ display: "flex", flexDirection: "column", gap: t.space.xl }}>
            <CostEstimateHeadline estimate={estimate} />
            <CostEstimateStageTable stages={estimate.stages} />
            <CostEstimateCaveats estimate={estimate} />
          </div>
        )}
      </div>
    </div>
  );
}
