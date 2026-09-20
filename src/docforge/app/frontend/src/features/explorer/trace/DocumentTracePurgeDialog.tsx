// ====== Code Summary ======
// Confirm modal for reclaiming a single document's stored heavy execution-trace payloads — the
// explorer-feature-local counterpart of `features/collections/trace/TracePurgeOfferDialog` (same
// visual shape, duplicated rather than cross-feature-imported — see that file's own note on the
// convention). Portaled to `document.body` — see PageBoxLightbox.tsx for why any `position: fixed`
// overlay in this app must be.

import { useId } from "react";
import { createPortal } from "react-dom";
import { Button } from "../../../components/Button";
import { useFocusTrap } from "../../../shell/useFocusTrap";
import { theme } from "../../../theme";

interface DocumentTracePurgeDialogProps {
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DocumentTracePurgeDialog({ pending, error, onConfirm, onCancel }: DocumentTracePurgeDialogProps) {
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
          background: theme.color.panel, border: `1px solid ${theme.color.error}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 440, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          Purge stored traces
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
          This reclaims every heavy full execution-trace payload stored for this document's jobs. The
          per-node summaries above stay intact — only the raw input/output payloads are removed.
        </div>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
            {pending ? "purging…" : "Confirm purge"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
