// ====== Code Summary ======
// Embeds the stage rail for one collection: seeds it with the collection's stored blob, PATCHes
// it back on save. The stage rail is the ONLY pipeline UI; the advanced surface (/inspect and
// /edit) stays headless — a future advanced mode would consume it through the API client.

import { useEffect, useState } from "react";
import { getCollection, updateCollection, type Collection } from "../../api/collections";
import type { GroupBlob } from "../../api/types";
import { BackLink } from "../../components/BackLink";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { StageRailPage } from "../stage-rail/StageRailPage";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";

interface CollectionPipelinePageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionPipelinePage({ collectionId, onNavigate }: CollectionPipelinePageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCollection(collectionId)
      .then((c) => { if (!cancelled) setCollection(c); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [collectionId]);

  if (error) return <ErrorState message={error} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: `${theme.space.xs}px ${theme.space.l}px 0` }}>
        <BackLink label={collection.name} onClick={() => onNavigate({ name: "collection", collectionId })} />
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <StageRailPage
          initialBlob={collection.pipeline as unknown as GroupBlob}
          onSave={async (blob) => {
            const updated = await updateCollection(collectionId, { pipeline: blob as unknown as Record<string, unknown> });
            setCollection(updated);
          }}
          title="Pipeline"
          subtitle={collection.name}
        />
      </div>
    </div>
  );
}
