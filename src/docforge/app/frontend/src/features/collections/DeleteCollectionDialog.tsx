// ====== Code Summary ======
// Modal confirm for deleting a whole collection — names the collection so a misclick never wipes
// the wrong one, and requires an explicit confirm click (no type-to-confirm; matches the strength
// of the existing edit-form Danger Zone confirm, see wizard/DangerZone.tsx). This is the shared
// confirm UI for the two newly-discoverable delete entry points (dashboard card overflow menu,
// collection detail header overflow menu); both drive it with `state/useDeleteCollection`. Danger
// Zone keeps its own inline (non-modal) confirm — same underlying hook, different presentation
// since it already lives on a dedicated settings screen. Portaled to `document.body`: several page
// wrappers in this app carry the `df-rise` entrance CSS animation, which silently confines an
// in-tree `position: fixed` overlay to that ancestor's box in Chromium (see PageBoxLightbox.tsx).

import { useId } from "react";
import { createPortal } from "react-dom";
import { Button } from "../../components/Button";
import { useFocusTrap } from "../../shell/useFocusTrap";
import { theme } from "../../theme";

interface DeleteCollectionDialogProps {
  collectionName: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteCollectionDialog({ collectionName, pending, error, onConfirm, onCancel }: DeleteCollectionDialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onCancel);

  return createPortal(
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", backdropFilter: "blur(2px)", zIndex: 100,
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
          position: "relative",
          background: theme.color.panel, border: `1px solid ${theme.color.error}`, borderRadius: theme.radius.l,
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 440, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <button
          type="button"
          onClick={onCancel}
          disabled={pending}
          title="Close"
          aria-label="Close"
          style={{
            position: "absolute", top: -12, right: -12, width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: theme.color.panel, color: theme.color.text,
            border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.pill,
            fontSize: theme.font.size.l, lineHeight: 1, cursor: pending ? "not-allowed" : "pointer",
            boxShadow: theme.shadow.pop,
          }}
        >
          ×
        </button>
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          Delete collection
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
          Deleting <strong style={{ color: theme.color.text }}>{collectionName}</strong> removes it and
          every document indexed under it. This cannot be undone.
        </div>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
            {pending ? "deleting…" : "Delete collection"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
