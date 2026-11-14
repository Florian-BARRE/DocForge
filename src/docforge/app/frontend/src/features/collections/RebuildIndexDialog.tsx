// ====== Code Summary ======
// Confirmation modal for "Rebuild index": explains what the rebuild does (declares the missing named
// vectors and refills the metadata vectors from Postgres — documents are NOT re-parsed or re-chunked)
// and that ingests are refused while it runs. The overlay shell is the shared `ConfirmDialog`.

import { ConfirmDialog } from "../../components/dialog/ConfirmDialog";
import { theme } from "../../theme";

interface RebuildIndexDialogProps {
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RebuildIndexDialog({ pending, error, onConfirm, onCancel }: RebuildIndexDialogProps) {
  return (
    <ConfirmDialog
      title="Rebuild the index?"
      confirmLabel="Rebuild index"
      pendingLabel="starting…"
      pending={pending}
      error={error ? `⚠ ${error}` : null}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ fontSize: theme.font.size.m, color: theme.color.text }}>
        Declares the vectors the current schema and embedder need, then refills the metadata vectors from the
        stored values. Documents are not re-parsed or re-chunked. New ingests are refused until it finishes.
      </div>
    </ConfirmDialog>
  );
}
