// ====== Code Summary ======
// The collection's Overview tab — a calm provider-availability dashboard. For an EMPTY collection (0
// documents) the FIRST thing on screen is the upload hero (CTA + "what happens next"); the provider
// health board follows below it as the drill-down, not the headline — an empty collection has nothing
// to ingest yet, so "how do I add something" outranks "is the plumbing healthy". A populated
// collection flips the order: the health board leads, then the normal quick-glance stat strip +
// storage + cost panels. Read-only; editing lives in the Metadata / Pipeline / Search studios.

import { useEffect, useState } from "react";
import { getCollection, getCollectionHealth, type Collection, type CollectionHealth } from "../../api/collections";
import { listDocuments, type DocumentListItem } from "../../api/explorer";
import { listJobs, type JobStatus } from "../../api/jobs";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { useHideHeaderUpload } from "./CollectionShell";
import { healthFixTarget, probeVerdict } from "./collectionHealth";
import { CostEstimatePanel } from "./estimate/CostEstimatePanel";
import { OverviewStatStrip } from "./OverviewStatStrip";
import { ProviderHealthBoard } from "./ProviderHealthBoard";
import { ReindexBanner } from "./ReindexBanner";
import { StorageFootprintPanel } from "./storage/StorageFootprintPanel";
import { UploadPanel } from "./UploadPanel";

interface Props {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionOverview({ collectionId, onNavigate }: Props) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [docs, setDocs] = useState<DocumentListItem[] | null>(null);
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<CollectionHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId).then(setCollection).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    listDocuments(collectionId).then(setDocs).catch(() => setDocs([]));
    listJobs(collectionId).then(setJobs).catch(() => setJobs([]));
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

  // An empty collection's hero below is the ONE active upload path — hide the shell header's
  // "Upload" toggle so it never opens a second, competing input alongside it. Must run before any
  // conditional return below (Rules of Hooks); tolerates docs === null.
  useHideHeaderUpload(docs !== null && docs.length === 0);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading overview…" />;

  const verdict = probeVerdict(health, healthError);
  // "empty" only means "stalled" (worth a Jobs-tab drill-down) when documents already exist — a
  // genuinely empty collection's fix IS the upload hero below, not a second button on the board.
  const fixTarget = healthFixTarget(health, collectionId, docs !== null && docs.length > 0);

  return (
    <div className="df-rise" style={{ padding: t.space.xl, overflowY: "auto", height: "100%", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
      {collection.needs_reindex && <div style={{ marginBottom: t.space.l }}><ReindexBanner /></div>}

      {docs && docs.length === 0 ? (
        <>
          <EmptyState
            icon="↑"
            title="Upload your first document"
            subtitle="This collection is empty — ingest a document to see it parsed, chunked and indexed for search."
          >
            <div style={{ display: "flex", flexDirection: "column", gap: t.space.l }}>
              <UploadPanel
                collectionId={collectionId}
                fields={collection.fields}
                onUploaded={(jobId, count) =>
                  onNavigate(count > 1 ? { name: "collection-jobs", collectionId } : { name: "job", collectionId, jobId })
                }
              />
              <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>
                What happens next: the file is parsed, enriched, chunked, contextualized and embedded —
                track progress from the job page this opens, or the Jobs tab any time.
              </div>
            </div>
          </EmptyState>

          {/* Still the drill-down for "can this empty collection even ingest right now" — kept
              below the upload CTA, not above it. */}
          <div style={{ marginTop: t.space.xl }}>
            <ProviderHealthBoard
              health={health} verdict={verdict} loading={healthLoading} error={healthError}
              onRecheck={recheckHealth} fixTarget={fixTarget} onNavigate={onNavigate}
            />
          </div>
        </>
      ) : (
        <>
          <ProviderHealthBoard
            health={health} verdict={verdict} loading={healthLoading} error={healthError}
            onRecheck={recheckHealth} fixTarget={fixTarget} onNavigate={onNavigate}
          />

          <OverviewStatStrip
            collection={collection}
            docs={docs}
            fields={collection.fields}
            health={health}
            jobs={jobs}
            collectionId={collectionId}
            onNavigate={onNavigate}
          />

          <div style={{ marginTop: t.space.xl }}>
            <StorageFootprintPanel collectionId={collectionId} onNavigate={onNavigate} />
          </div>

          <div>
            <CostEstimatePanel
              collectionId={collectionId}
              estimateOverrides={collection.estimate_overrides}
              onOverridesSaved={(overrides) =>
                setCollection((prev) => (prev ? { ...prev, estimate_overrides: overrides } : prev))
              }
            />
          </div>
        </>
      )}
    </div>
  );
}
