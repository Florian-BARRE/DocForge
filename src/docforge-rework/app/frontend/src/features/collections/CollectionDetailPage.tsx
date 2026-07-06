// ====== Code Summary ======
// A collection's contract page: summary + schema table, and the actions the brief asks for —
// edit collection (its own view, wizard reused in edit mode), edit pipeline (own view, embedding
// the studio), documents (own view, the document explorer), jobs (own view), upload (inline
// panel). Surfaces a prominent banner whenever `needs_reindex` is true — a page remount (e.g.
// returning from an edit) always refetches it.

import { useEffect, useState } from "react";
import { deleteCollection, getCollection, type Collection } from "../../api/collections";
import { BackLink } from "../../components/BackLink";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { ReindexBanner } from "./ReindexBanner";
import { SchemaTable } from "./SchemaTable";
import { UploadPanel } from "./UploadPanel";

interface CollectionDetailPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CollectionDetailPage({ collectionId, onNavigate }: CollectionDetailPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
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
    <div style={{ padding: theme.space.l, overflowY: "auto", height: "100%" }}>
      <BackLink label="Collections" onClick={() => onNavigate({ name: "collections" })} />
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, margin: `${theme.space.s}px 0` }}>
        <h1 style={{ fontSize: theme.font.size.xl }}>{collection.name}</h1>
        {collection.needs_reindex && <Chip tone="warn">needs reindex</Chip>}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: theme.space.s }}>
        {collection.supported_formats.map((f) => <Chip key={f} tone="accent">{f}</Chip>)}
      </div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, marginBottom: theme.space.l }}>
        Max file size: {(collection.max_file_size_bytes / (1024 * 1024)).toFixed(1)} MB · {collection.fields.length} field(s)
      </div>

      {collection.needs_reindex && <ReindexBanner />}

      <div style={{ display: "flex", gap: theme.space.s, marginBottom: theme.space.l }}>
        <Button onClick={() => onNavigate({ name: "collection-edit", collectionId })}>Edit collection</Button>
        <Button onClick={() => onNavigate({ name: "collection-pipeline", collectionId })}>Edit pipeline</Button>
        <Button onClick={() => onNavigate({ name: "collection-documents", collectionId })}>Documents</Button>
        <Button onClick={() => onNavigate({ name: "collection-jobs", collectionId })}>Jobs</Button>
        <Button onClick={() => setShowUpload((v) => !v)}>{showUpload ? "Hide upload" : "Upload"}</Button>
        <div style={{ marginLeft: "auto", display: "flex", gap: theme.space.s }}>
          {confirmingDelete ? (
            <>
              <span style={{ color: theme.color.dim, fontSize: theme.font.size.s, alignSelf: "center" }}>Delete for good?</span>
              <Button variant="danger" disabled={deleting} onClick={handleDelete}>{deleting ? "deleting…" : "Confirm delete"}</Button>
              <Button onClick={() => setConfirmingDelete(false)}>Cancel</Button>
            </>
          ) : (
            <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete</Button>
          )}
        </div>
      </div>

      {showUpload && (
        <div style={{ marginBottom: theme.space.l }}>
          <UploadPanel
            collectionId={collectionId}
            fields={collection.fields}
            onUploaded={(jobId) => onNavigate({ name: "job", collectionId, jobId })}
          />
        </div>
      )}

      <h2 style={{ fontSize: theme.font.size.l, marginBottom: theme.space.s }}>Schema</h2>
      <SchemaTable fields={collection.fields} />
    </div>
  );
}
