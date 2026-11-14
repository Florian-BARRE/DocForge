// ====== Code Summary ======
// Confirm modal for reclaiming a single document's stored heavy execution-trace payloads — the
// explorer-feature-local counterpart of `features/collections/trace/TracePurgeOfferDialog`. The
// overlay shell is the shared `ConfirmDialog`.

import { ConfirmDialog } from "../../../components/dialog/ConfirmDialog";
import { theme } from "../../../theme";

interface DocumentTracePurgeDialogProps {
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DocumentTracePurgeDialog({ pending, error, onConfirm, onCancel }: DocumentTracePurgeDialogProps) {
  return (
    <ConfirmDialog
      title="Purge stored traces"
      tone="danger"
      maxWidth={440}
      confirmVariant="danger"
      confirmLabel="Confirm purge"
      pendingLabel="purging…"
      pending={pending}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
        This reclaims every heavy full execution-trace payload stored for this document's jobs. The
        per-node summaries above stay intact — only the raw input/output payloads are removed.
      </div>
    </ConfirmDialog>
  );
}
