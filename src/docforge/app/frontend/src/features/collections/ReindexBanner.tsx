// ====== Code Summary ======
// A prominent warning banner for a collection's detail page — shown whenever `needs_reindex` is
// true or the vector store lacks named vectors the schema/embedder need (`missing_vectors`), whether
// that state predates this visit or was just set by an edit (searchable-schema flags, or a change of
// the embed dense/sparse provider). Offers the "Rebuild index" action behind a confirm dialog.

import { useState } from "react";
import { rebuildCollectionIndex, type Collection } from "../../api/collections";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";
import { RebuildIndexDialog } from "./RebuildIndexDialog";

interface ReindexBannerProps {
  collection: Pick<Collection, "id" | "needs_reindex" | "missing_vectors">;
  /** Fired once the rebuild job is queued, so the parent can refetch the collection. */
  onStarted?: () => void;
}

export function reindexNeeded(collection: Pick<Collection, "needs_reindex" | "missing_vectors">): boolean {
  return collection.needs_reindex || (collection.missing_vectors?.length ?? 0) > 0;
}

export function ReindexBanner({ collection, onStarted }: ReindexBannerProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = collection.missing_vectors ?? [];

  const start = () => {
    setPending(true);
    setError(null);
    rebuildCollectionIndex(collection.id)
      .then(() => {
        setConfirming(false);
        toast.success("Index rebuild started — track it in Activity");
        onStarted?.();
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setPending(false));
  };

  return (
    <div
      style={{
        background: theme.color.warnSoft, border: `1px solid ${theme.color.warn}`, borderRadius: theme.radius.m,
        padding: `${theme.space.s}px ${theme.space.m}px`, color: theme.color.warn, fontSize: theme.font.size.s,
        marginBottom: theme.space.l, display: "flex", alignItems: "center", gap: theme.space.m, flexWrap: "wrap",
      }}
    >
      <span style={{ flex: 1, minWidth: 240 }}>
        Searchable schema or embedder changed — existing documents need reindexing
        {missing.length > 0 && (
          <>
            {" "}(missing vectors: <span style={{ fontFamily: theme.font.mono }}>{missing.join(", ")}</span>)
          </>
        )}.
      </span>
      <Button size="sm" variant="secondary" onClick={() => setConfirming(true)}>Rebuild index</Button>
      {confirming && (
        <RebuildIndexDialog pending={pending} error={error} onConfirm={start} onCancel={() => setConfirming(false)} />
      )}
    </div>
  );
}
