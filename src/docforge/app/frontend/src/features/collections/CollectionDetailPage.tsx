// ====== Code Summary ======
// The collection's Metadata tab content (Corpus › Metadata), beneath CollectionShell's header/tabs:
// the reindex banner (when the searchable surface has drifted), the editable metadata-field schema
// table, and the destructive delete flow — the one action deliberately kept off the persistent shell
// header. A page remount (e.g. returning from an edit) always refetches it.

import { useEffect, useState } from "react";
import { deleteCollection, getCollection, type Collection } from "../../api/collections";
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
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteCollection(collectionId);
      onNavigate({ name: "collections" });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  };

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

      <div
        style={{
          marginTop: theme.space.xxl, paddingTop: theme.space.l, borderTop: `1px solid ${theme.color.line}`,
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m,
        }}
      >
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
          Deleting a collection removes it and every document indexed under it. This cannot be undone.
        </div>
        <div style={{ display: "flex", gap: theme.space.s, flexShrink: 0 }}>
          {confirmingDelete ? (
            <>
              <Button onClick={() => setConfirmingDelete(false)} disabled={deleting}>Cancel</Button>
              <Button variant="danger" disabled={deleting} onClick={handleDelete}>
                {deleting ? "deleting…" : "Confirm delete"}
              </Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete collection</Button>
          )}
        </div>
      </div>
    </div>
  );
}
