// ====== Code Summary ======
// A modal confirm for a bulk operation — always names the affected count before committing,
// since delete/re-ingest are expensive or destructive at grid scale. The overlay shell is the
// shared `ConfirmDialog`; this one stays in-tree (no portal) and ignores backdrop clicks, as before.

import type { ReactNode } from "react";
import type { ButtonVariant } from "../../components/Button";
import { ConfirmDialog } from "../../components/dialog/ConfirmDialog";
import { theme } from "../../theme";

interface BulkConfirmDialogProps {
  title: string;
  description: string;
  count: number;
  confirmLabel: string;
  variant: ButtonVariant;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Extra controls/notices between the count and the buttons (e.g. the reingest stage choice). */
  children?: ReactNode;
}

export function BulkConfirmDialog({ title, description, count, confirmLabel, variant, pending, onConfirm, onCancel, children }: BulkConfirmDialogProps) {
  return (
    <ConfirmDialog
      title={title}
      tone="accent"
      maxWidth={440}
      portal={false}
      closeOnBackdrop={false}
      confirmVariant={variant}
      confirmLabel={confirmLabel}
      pendingLabel="working…"
      pending={pending}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>{description}</div>
      <div style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xl, color: theme.color.accentSafe, fontWeight: 700 }}>
        {count.toLocaleString()} document{count === 1 ? "" : "s"}
      </div>
      {children}
    </ConfirmDialog>
  );
}
