// ====== Code Summary ======
// The collection Overview's "Storage footprint" card — self-fetches GET .../storage (a heavier,
// separate accounting sweep from the rest of the Overview) so it never blocks the page's own
// collection/health fetches. Renders the grand total, the three-store segmented bar, each store's
// collapsible sub-breakdown, and the per-document table.

import { useEffect, useState } from "react";
import { fetchCollectionStorage, type CollectionStorage } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import type { Navigate } from "../../../shell/view";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { DocumentStorageTable } from "./DocumentStorageTable";
import { StorageBar } from "./StorageBar";
import { StorageGrandTotal } from "./StorageGrandTotal";
import { STORAGE_STORES } from "./storageStores";
import { StorageStoreBreakdown } from "./StorageStoreBreakdown";

interface StorageFootprintPanelProps {
  collectionId: string;
  onNavigate: Navigate;
}

interface StoreBreakdownContent {
  rows: { label: string; value: string }[];
  note?: string;
}

function storeBreakdowns(storage: CollectionStorage): Record<"s3" | "postgres" | "qdrant", StoreBreakdownContent> {
  const { s3, postgres, qdrant } = storage;
  const s3DedupNote =
    s3.physical_unique_bytes !== s3.total_bytes
      ? `Deduplicated on disk: ${formatBytes(s3.physical_unique_bytes)} physical (saves ${formatBytes(s3.total_bytes - s3.physical_unique_bytes)}).`
      : undefined;

  return {
    s3: { rows: [{ label: "Original files", value: formatBytes(s3.original_bytes) }, { label: "Rendered views", value: formatBytes(s3.rendered_bytes) }], note: s3DedupNote },
    postgres: {
      rows: [
        { label: "Documents", value: formatBytes(postgres.documents_bytes) },
        { label: "IR blocks", value: formatBytes(postgres.ir_blocks_bytes) },
        { label: "Enrichment", value: formatBytes(postgres.enrichment_bytes) },
        { label: "Chunks", value: formatBytes(postgres.chunks_bytes) },
        { label: "Metadata", value: formatBytes(postgres.metadata_bytes) },
        { label: "Observability", value: formatBytes(postgres.observability_bytes) },
      ],
    },
    qdrant: {
      rows: [
        { label: "Points", value: qdrant.points.toLocaleString() },
        { label: "Dense vectors", value: formatBytes(qdrant.dense_bytes) },
        { label: "Sparse vectors", value: formatBytes(qdrant.sparse_bytes) },
        { label: "Payload", value: formatBytes(qdrant.payload_bytes) },
      ],
    },
  };
}

export function StorageFootprintPanel({ collectionId, onNavigate }: StorageFootprintPanelProps) {
  const [storage, setStorage] = useState<CollectionStorage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchCollectionStorage(collectionId)
      .then(setStorage)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [collectionId]);

  const breakdowns = storage ? storeBreakdowns(storage) : null;

  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, marginBottom: t.space.l, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m, padding: `${t.space.m}px ${t.space.l}px`, borderBottom: `1px solid ${t.color.line}` }}>
        <span style={{ fontFamily: t.font.display, fontWeight: t.font.weight.bold, fontSize: t.font.size.xl, color: t.color.text }}>
          Storage footprint
        </span>
        <div style={{ marginLeft: "auto" }}>
          <Button size="sm" variant="ghost" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</Button>
        </div>
      </div>

      <div style={{ padding: t.space.l }}>
        {error && <ErrorState message={error} onRetry={load} />}
        {!error && !storage && <LoadingState label="accounting storage…" />}
        {!error && storage && breakdowns && (
          storage.grand_total_bytes === 0 ? (
            <div style={{ color: t.color.dim, fontSize: t.font.size.m, textAlign: "center", padding: t.space.xl }}>
              No storage used yet — ingest a document to see its footprint.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: t.space.xl }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: t.space.l }}>
                <StorageGrandTotal bytes={storage.grand_total_bytes} />
                <div style={{ flex: "1 1 320px", minWidth: 260 }}>
                  <StorageBar storage={storage} />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: t.space.m }}>
                {STORAGE_STORES.map(({ key, label, color }) => {
                  const stats = storage[key];
                  return (
                    <StorageStoreBreakdown
                      key={key}
                      label={label}
                      swatchColor={color}
                      totalBytes={stats.total_bytes}
                      estimated={stats.estimated}
                      rows={breakdowns[key].rows}
                      note={breakdowns[key].note}
                    />
                  );
                })}
              </div>

              <div>
                <div style={{ fontFamily: t.font.display, fontWeight: t.font.weight.semibold, fontSize: t.font.size.l, color: t.color.text, marginBottom: t.space.s }}>
                  By document
                </div>
                <DocumentStorageTable documents={storage.documents} collectionId={collectionId} onNavigate={onNavigate} />
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}
