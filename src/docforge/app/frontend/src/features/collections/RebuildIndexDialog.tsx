// ====== Code Summary ======
// Confirmation modal for "Rebuild index": explains what the rebuild does (declares the missing named
// vectors and refills the metadata vectors from Postgres — documents are NOT re-parsed or re-chunked)
// and that ingests are refused while it runs. Portaled to `document.body` like the other dialogs.

import { useId } from "react";
import { createPortal } from "react-dom";
import { Button } from "../../components/Button";
import { useFocusTrap } from "../../shell/useFocusTrap";
import { theme } from "../../theme";

interface RebuildIndexDialogProps {
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RebuildIndexDialog({ pending, error, onConfirm, onCancel }: RebuildIndexDialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onCancel);
  return createPortal(
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, background: theme.color.overlay, backdropFilter: "blur(2px)", zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "center", padding: theme.space.l,
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: theme.color.panel, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 480, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          Rebuild the index?
        </h2>
        <div style={{ fontSize: theme.font.size.m, color: theme.color.text }}>
          Declares the vectors the current schema and embedder need, then refills the metadata vectors from the
          stored values. Documents are not re-parsed or re-chunked. New ingests are refused until it finishes.
        </div>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>⚠ {error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={pending} onClick={onConfirm}>
            {pending ? "starting…" : "Rebuild index"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
