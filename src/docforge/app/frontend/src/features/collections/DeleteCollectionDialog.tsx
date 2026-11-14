// ====== Code Summary ======
// Modal confirm for deleting a whole collection — names the collection so a misclick never wipes
// the wrong one, and requires an explicit confirm click (no type-to-confirm; matches the strength
// of the Settings ▸ Danger zone confirm, see settings/DangerZone.tsx). This is the confirm UI for
// the dashboard card's overflow-menu delete entry point (CollectionCard.tsx) — driven by the same
// `state/useDeleteCollection` hook Danger Zone uses, which keeps its own inline (non-modal) confirm
// instead since it already lives on a dedicated settings screen. The overlay shell (portal, focus
// trap, Escape, "×" close) is the shared `ConfirmDialog`.

import { ConfirmDialog } from "../../components/dialog/ConfirmDialog";
import { theme } from "../../theme";

interface DeleteCollectionDialogProps {
  collectionName: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteCollectionDialog({ collectionName, pending, error, onConfirm, onCancel }: DeleteCollectionDialogProps) {
  return (
    <ConfirmDialog
      title="Delete collection"
      tone="danger"
      maxWidth={440}
      showClose
      confirmVariant="danger"
      confirmLabel="Delete collection"
      pendingLabel="deleting…"
      pending={pending}
      error={error}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
        Deleting <strong style={{ color: theme.color.text }}>{collectionName}</strong> removes it and
        every document indexed under it. This cannot be undone.
      </div>
    </ConfirmDialog>
  );
}
