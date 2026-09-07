// ====== Code Summary ======
// The collection Overview's "Cost estimate" card — sits beside StorageFootprintPanel but is
// explicitly user-triggered rather than self-fetched on mount: a dry-run sweep is heavier than a
// glance-worthy stat, and an auto-fetched estimate could go stale silently. Pick a scope
// (pending-only vs the whole collection), click "Estimate cost", and the panel renders the
// projected spend + volume of ingesting — read-only, triggers no job.

import { useState } from "react";
import { estimateCollectionCost, type CostEstimate, type EstimateOverrides, type EstimateScope } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { TabNav } from "../../../components/TabNav";
import { theme as t } from "../../../theme";
import { buildDocumentFilter } from "../../corpus/filterBuilder";
import { countActiveFilters, type ColumnFiltersState } from "../../corpus/types";
import { CostEstimateCaveats } from "./CostEstimateCaveats";
import { CostEstimateHeadline } from "./CostEstimateHeadline";
import { CostEstimateStageTable } from "./CostEstimateStageTable";
import { EstimateOverridesEditor } from "./EstimateOverridesEditor";
import { EstimateSubsetFilterPanel } from "./EstimateSubsetFilterPanel";

interface CostEstimatePanelProps {
  collectionId: string;
  /** The collection's registered file formats — feeds the "Selected documents" filter's Format
   *  control, mirroring the corpus grid's own column options. */
  supportedFormats: string[];
  /** The collection's stored per-collection cost-estimate overrides — surfaced in the editable
   *  "Assumptions & rates" section below the result. */
  estimateOverrides: EstimateOverrides | null;
  /** Fired once the overrides editor persists a change, so the owning page's Collection state stays
   *  in sync without a full reload. */
  onOverridesSaved: (overrides: EstimateOverrides | null) => void;
}

/** The panel's own scope selector — a superset of the API's `EstimateScope`: "filter" is a local
 *  UI state (a subset selector, not a whole-collection default) that resolves to a `filter` body
 *  on run, never sent to the endpoint as a `scope` value. */
type PanelScope = EstimateScope | "filter";

const SCOPE_TABS: { key: PanelScope; label: string }[] = [
  { key: "pending", label: "Pending only" },
  { key: "all", label: "Whole collection" },
  { key: "filter", label: "Selected documents" },
];

/** What the run button is about to cover — shown so the chosen perimeter is never a guess. */
function scopeCaption(scope: PanelScope, activeFilterCount: number): string {
  if (scope === "pending") return "Not-yet-ingested documents only.";
  if (scope === "all") return "Every document in the collection.";
  if (activeFilterCount === 0) return "No filters applied yet — matches the whole collection.";
  return `Documents matching ${activeFilterCount} filter${activeFilterCount === 1 ? "" : "s"} below.`;
}

export function CostEstimatePanel({ collectionId, supportedFormats, estimateOverrides, onOverridesSaved }: CostEstimatePanelProps) {
  const [scope, setScope] = useState<PanelScope>("pending");
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>({});
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeFilterCount = countActiveFilters(columnFilters);

  const run = () => {
    setLoading(true);
    setError(null);
    const request =
      scope === "filter"
        ? estimateCollectionCost(collectionId, "pending", { filter: buildDocumentFilter(columnFilters) })
        : estimateCollectionCost(collectionId, scope);
    request
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

      <div style={{ padding: t.space.l, display: "flex", flexDirection: "column", gap: t.space.l }}>
        <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>{scopeCaption(scope, activeFilterCount)}</div>
        {scope === "filter" && (
          <EstimateSubsetFilterPanel
            columnFilters={columnFilters}
            onColumnFilterChange={(columnId, value) => setColumnFilters((prev) => ({ ...prev, [columnId]: value }))}
            onClearAll={() => setColumnFilters({})}
            supportedFormats={supportedFormats}
          />
        )}
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
        <div style={{ marginTop: t.space.l }}>
          <EstimateOverridesEditor
            collectionId={collectionId}
            overrides={estimateOverrides}
            stages={estimate?.stages ?? []}
            assumptionPlaceholders={estimate?.assumptions ?? null}
            onSaved={onOverridesSaved}
          />
        </div>
      </div>
    </div>
  );
}
