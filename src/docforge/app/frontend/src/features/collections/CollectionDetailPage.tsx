// ====== Code Summary ======
// The collection's Metadata tab content (Corpus › Metadata), beneath CollectionShell's header/tabs:
// the reindex banner (when the searchable surface has drifted) and the editable metadata-field
// schema table. The destructive delete flow lives on the Edit page's danger zone instead (see
// `wizard/DangerZone.tsx`) — a settings action, not something to trip over while reading fields. A
// page remount (e.g. returning from an edit) always refetches it.

import { useEffect, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { Button } from "../../components/Button";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ReindexBanner } from "./ReindexBanner";
import { SchemaTable } from "./SchemaTable";

interface CollectionDetailPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionDetailPage({ collectionId, onNavigate }: CollectionDetailPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  return (
    <div style={{ padding: theme.space.xl, maxWidth: 1200, margin: "0 auto", overflowY: "auto", height: "100%" }}>
      {collection.needs_reindex && <ReindexBanner />}

      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.m, marginBottom: theme.space.m }}>
        <h2 style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700 }}>
          Metadata
        </h2>
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          the fields upstream of ingestion — each drives filtering, semantic or lexical search
        </span>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="secondary" onClick={() => onNavigate({ name: "collection-edit", collectionId })}>
            Edit fields
          </Button>
        </div>
      </div>
      <SchemaTable fields={collection.fields} />
    </div>
  );
}
