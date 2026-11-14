// ====== Code Summary ======
// A confirm/cancel modal on top of `Dialog`: a title, the caller's body (`children`), an optional
// error line and the right-aligned footer — a Cancel button and the confirm button, both disabled
// while `pending`, the confirm one showing `pendingLabel` meanwhile. Every confirm dialog of the app
// (delete, rebuild, restore, switch alias, bulk action, schema change, trace purge) is this shell
// with its own body; the shell options (`tone`, `maxWidth`, `blur`, `portal`, `closeOnBackdrop`,
// `showClose`) pass straight through to `Dialog`.

// ====== Third-Party Library Imports ======
import type { ReactNode } from "react";

// ====== Internal Project Imports ======
import { theme } from "../../theme";
import { Button, type ButtonVariant } from "../Button";

// ====== Local Project Imports ======
import { Dialog, type DialogProps } from "./Dialog";

type ForwardedDialogProps = Pick<DialogProps, "tone" | "maxWidth" | "blur" | "portal" | "closeOnBackdrop" | "showClose">;

interface ConfirmDialogProps extends ForwardedDialogProps {
  title: ReactNode;
  confirmLabel: ReactNode;
  /** Shown on the confirm button while `pending`. */
  pendingLabel: ReactNode;
  /** Cancel's label. Default "Cancel". */
  cancelLabel?: ReactNode;
  confirmVariant?: ButtonVariant;
  pending?: boolean;
  /** Disables the confirm button on top of `pending` (e.g. a diff still loading). */
  confirmDisabled?: boolean;
  /** Rendered in the error ink between the body and the footer. */
  error?: ReactNode;
  onConfirm: () => void;
  /** Cancel button, Escape, backdrop click and the "×" button. */
  onCancel: () => void;
  children?: ReactNode;
}

export function ConfirmDialog({
  title, confirmLabel, pendingLabel, cancelLabel = "Cancel", confirmVariant = "primary", pending = false,
  confirmDisabled = false, error, onConfirm, onCancel, children, ...shell
}: ConfirmDialogProps) {
  return (
    <Dialog {...shell} title={title} onClose={onCancel} closeDisabled={pending}>
      {children}
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
      <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
        <Button size="sm" disabled={pending} onClick={onCancel}>{cancelLabel}</Button>
        <Button variant={confirmVariant} size="sm" disabled={pending || confirmDisabled} onClick={onConfirm}>
          {pending ? pendingLabel : confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
