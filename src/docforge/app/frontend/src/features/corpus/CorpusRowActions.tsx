// ====== Code Summary ======
// One row's quick actions — a compact re-ingest button immediately to the LEFT of the delete
// button. Re-ingest fires immediately (a toast is enough, like the enabled toggle); delete keeps
// the app's usual two-step inline confirm (same shape as the old DocumentRow's).

import { useState } from "react";
import { reingestDocument } from "../../api/documents";
import { HttpError } from "../../api/http";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";

interface CorpusRowActionsProps {
  documentId: string;
  onDelete: () => Promise<void>;
}

export function CorpusRowActions({ documentId, onDelete }: CorpusRowActionsProps) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [reingesting, setReingesting] = useState(false);

  const handleReingest = async () => {
    setReingesting(true);
    try {
      await reingestDocument(documentId);
      toast.success("Re-ingestion queued — see the Jobs tab");
    } catch (e) {
      toast.error(e instanceof HttpError ? e.message : String(e));
    } finally {
      setReingesting(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
      // No local reset on success — the row disappears once the parent refetches.
    } catch (e) {
      setDeleting(false);
      setConfirming(false);
      toast.error(e instanceof HttpError ? e.message : String(e));
    }
  };

  if (confirming) {
    return (
      <span style={{ display: "inline-flex", gap: theme.space.xs, alignItems: "center" }}>
        <Button variant="danger" size="sm" disabled={deleting} onClick={handleDelete}>{deleting ? "…" : "confirm"}</Button>
        <Button size="sm" disabled={deleting} onClick={() => setConfirming(false)}>cancel</Button>
      </span>
    );
  }

  return (
    <span style={{ display: "inline-flex", gap: theme.space.xs, alignItems: "center" }}>
      <Button
        variant="primary"
        size="sm"
        disabled={reingesting}
        onClick={handleReingest}
        title="Re-run the full pipeline on this document"
        aria-label="Re-ingest this document"
      >
        {reingesting ? "…" : "⟳"}
      </Button>
      <Button variant="danger" size="sm" onClick={() => setConfirming(true)}>delete</Button>
    </span>
  );
}
