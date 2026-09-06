// ====== Code Summary ======
// Two Home tiles derived from the fleet's live health probes: how many collections need attention
// right now vs. how many are fully operational — each clicks through to the matching Collections
// preset. Deliberately imports `useCollectionsFleet` directly (a cross-feature import, an EXCEPTION
// to the usual feature-slice isolation for small pure helpers — see agent-memory/frontend/
// feature_slice_isolation.md): that hook owns a real multi-endpoint fetch/fan-out orchestration
// (list + per-collection health/doc-count/queue probes), and duplicating that is exactly the kind
// of large stateful logic the isolation rule was never meant to force-duplicate.

import { StatTile } from "../../components/StatTile";
import type { Navigate } from "../../shell/view";
import { useCollectionsFleet, type FleetEntry } from "../collections/state/useCollectionsFleet";

/** Mirrors CollectionsToolbar's own "attention" bucket (down/degraded/ingest_unavailable). */
function needsAttention(entry: FleetEntry): boolean {
  const verdict = entry.health?.verdict;
  return verdict === "down" || verdict === "degraded" || verdict === "ingest_unavailable";
}

interface CollectionsStatusTilesProps {
  onNavigate: Navigate;
}

export function CollectionsStatusTiles({ onNavigate }: CollectionsStatusTilesProps) {
  const { collections, visibleEntries } = useCollectionsFleet("all");

  if (!collections) {
    return (
      <>
        <StatTile value="…" label="Need attention" />
        <StatTile value="…" label="Operational" />
      </>
    );
  }

  const attentionCount = visibleEntries.filter(needsAttention).length;
  const operationalCount = visibleEntries.filter((e) => e.health?.verdict === "operational").length;

  return (
    <>
      <StatTile
        value={attentionCount}
        label="Need attention"
        tone={attentionCount > 0 ? "warn" : "neutral"}
        caption="down · degraded · ingest unavailable"
        onClick={() => onNavigate({ name: "collections", health: "attention" })}
      />
      <StatTile
        value={operationalCount}
        label="Operational"
        tone="ok"
        caption={`of ${collections.length} collection${collections.length === 1 ? "" : "s"}`}
        onClick={() => onNavigate({ name: "collections", health: "operational" })}
      />
    </>
  );
}
