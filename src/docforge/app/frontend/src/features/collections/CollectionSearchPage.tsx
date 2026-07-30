// ====== Code Summary ======
// Embeds the search pipeline editor for one collection: seeds it with the collection's stored
// `search` blob (falling back to the product default when the stored value is the `{}` sentinel —
// every collection carries that today, meaning "use the stock default"), PATCHes it back on save.
// Nested under CollectionShell (which already provides the back navigation and tab strip), so this
// page is just the editor's own full-bleed canvas — no extra chrome of its own.

import { useEffect, useState } from "react";
import { getCollection, updateCollection, type Collection } from "../../api/collections";
import type { GroupBlob } from "../../api/types";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { SearchPipelineEditor } from "../search-pipeline/SearchPipelineEditor";
import type { Navigate } from "../../shell/view";

interface CollectionSearchPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

/** `{}` is the "use stock default" sentinel; only a real graph (carrying `"nodes"`) seeds the editor. */
function seedBlob(search: Record<string, unknown>): GroupBlob | undefined {
  return "nodes" in search ? (search as unknown as GroupBlob) : undefined;
}

export function CollectionSearchPage({ collectionId }: CollectionSearchPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Bumped after a server-side reset so the editor remounts and re-seeds from the fresh (now
  // sentinel-backed) collection.search, instead of quietly keeping the just-replaced local draft.
  const [resetVersion, setResetVersion] = useState(0);

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
    <div style={{ height: "100%" }}>
      <SearchPipelineEditor
        key={resetVersion}
        initialBlob={seedBlob(collection.search)}
        onSave={async (blob) => {
          const updated = await updateCollection(collectionId, { search: blob as unknown as Record<string, unknown> });
          setCollection(updated);
        }}
        onResetToDefault={async () => {
          const updated = await updateCollection(collectionId, { search: {} });
          setCollection(updated);
          setResetVersion((v) => v + 1);
        }}
      />
    </div>
  );
}
