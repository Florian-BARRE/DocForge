// ====== Code Summary ======
// The document page header's action cluster: the searchable toggle, re-ingest, and a delete flow
// gated behind an inline confirm step — a self-contained slice of the page (owns its own
// deleting/reingesting/confirm state) so `DocumentPage` only has to render it and react to its
// two terminal outcomes (navigate away on delete, jump to the new job on re-ingest).

import { useState } from "react";
import { deleteDocument } from "../../api/explorer";
import { reingestDocument } from "../../api/documents";
import { Button } from "../../components/Button";
import { theme } from "../../theme";
import type { Navigate } from "../../shell/view";
import { useToast } from "../../shell/toast";
import { DocumentEnabledToggle } from "./DocumentEnabledToggle";

interface DocumentPageActionsProps {
  documentId: string;
  collectionId: string;
  enabled: boolean;
  onEnabledChanged: (enabled: boolean) => void;
  onNavigate: Navigate;
  /** Bubbles a delete/re-ingest failure up to the page's own error state. */
  onError: (message: string) => void;
}

export function DocumentPageActions({
  documentId, collectionId, enabled, onEnabledChanged, onNavigate, onError,
}: DocumentPageActionsProps) {
  const toast = useToast();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reingesting, setReingesting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteDocument(documentId);
      onNavigate({ name: "collection-documents", collectionId });
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  };

  const handleReingest = async () => {
    setReingesting(true);
    try {
      // Re-runs the stored original through the collection's current pipeline — no re-upload. Jump
      // to the new job so its progress (and the live stage feed) is watched straight away.
      const { job_id } = await reingestDocument(documentId);
      toast.success("Re-ingest started");
      onNavigate({ name: "job", collectionId, jobId: job_id });
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
      setReingesting(false);
    }
  };

  return (
    <>
      <DocumentEnabledToggle documentId={documentId} enabled={enabled} onChanged={onEnabledChanged} />
      <Button onClick={handleReingest} disabled={reingesting}>{reingesting ? "re-ingesting…" : "Re-ingest"}</Button>
      {confirmingDelete ? (
        <span style={{ display: "inline-flex", gap: theme.space.s, alignItems: "center" }}>
          <span style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>Delete for good?</span>
          <Button variant="danger" disabled={deleting} onClick={handleDelete}>{deleting ? "deleting…" : "Confirm delete"}</Button>
          <Button onClick={() => setConfirmingDelete(false)}>Cancel</Button>
        </span>
      ) : (
        <Button variant="danger" onClick={() => setConfirmingDelete(true)}>Delete document</Button>
      )}
    </>
  );
}
