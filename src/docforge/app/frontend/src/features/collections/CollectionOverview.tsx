// ====== Code Summary ======
// The collection's Overview tab — a calm provider-availability dashboard. The hero is the live
// provider health board (grouped Ingest/Search, probed on mount + "Re-check"), whose verdict is a
// pure projection of that probe; below it a slim strip of quick-glance stat chips links out to the
// tabs that own the detail (past job/document failures live in the Jobs tab, not here). Read-only;
// editing lives in the Metadata / Pipeline / Search studios.

import { useEffect, useState } from "react";
import { getCollection, getCollectionHealth, type Collection, type CollectionHealth } from "../../api/collections";
import { listDocuments, type DocumentListItem } from "../../api/explorer";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { probeVerdict } from "./collectionHealth";
import { CostEstimatePanel } from "./estimate/CostEstimatePanel";
import { OverviewStatStrip } from "./OverviewStatStrip";
import { ProviderHealthBoard } from "./ProviderHealthBoard";
import { ReindexBanner } from "./ReindexBanner";
import { StorageFootprintPanel } from "./storage/StorageFootprintPanel";

interface Props {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionOverview({ collectionId, onNavigate }: Props) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [docs, setDocs] = useState<DocumentListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<CollectionHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId).then(setCollection).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    listDocuments(collectionId).then(setDocs).catch(() => setDocs([]));
  };
  useEffect(load, [collectionId]);

  // Re-runs the on-demand provider probe — used on mount and by every "Re-check" control. A failed
  // re-check keeps the last-known-good `health` on screen (only the error note updates) so a
  // transient probe-fetch hiccup doesn't wipe a previously confirmed verdict back to "unknown".
  const recheckHealth = () => {
    setHealthLoading(true);
    setHealthError(null);
    getCollectionHealth(collectionId)
      .then((result) => setHealth(result))
      .catch((e) => setHealthError(e instanceof Error ? e.message : String(e)))
      .finally(() => setHealthLoading(false));
  };
  useEffect(recheckHealth, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading overview…" />;

  const verdict = probeVerdict(health, healthError);

  return (
    <div className="df-rise" style={{ padding: t.space.xl, overflowY: "auto", height: "100%", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
      {collection.needs_reindex && <div style={{ marginBottom: t.space.l }}><ReindexBanner /></div>}

      <ProviderHealthBoard health={health} verdict={verdict} loading={healthLoading} error={healthError} onRecheck={recheckHealth} />

      <OverviewStatStrip
        collection={collection}
        docs={docs}
        fields={collection.fields}
        health={health}
        collectionId={collectionId}
        onNavigate={onNavigate}
      />

      <div style={{ marginTop: t.space.xl }}>
        <StorageFootprintPanel collectionId={collectionId} onNavigate={onNavigate} />
      </div>

      <div>
        <CostEstimatePanel collectionId={collectionId} />
      </div>
    </div>
  );
}
