// ====== Code Summary ======
// Modal confirm for pointing a collection alias at THIS collection (the blue/green switch). Every
// client and every `alias:<name>` key scope follows the alias on the very next request, so the switch
// is never a single click. Portaled to document.body for the same `df-rise` reason as
// DeleteCollectionDialog.

import { useId } from "react";
import { createPortal } from "react-dom";
import { Button } from "../../../components/Button";
import { useFocusTrap } from "../../../shell/useFocusTrap";
import { theme } from "../../../theme";

interface SwitchAliasDialogProps {
  alias: string;
  /** The collection the alias points at now; null when the alias does not exist yet. */
  currentTargetName: string | null;
  collectionName: string;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SwitchAliasDialog({ alias, currentTargetName, collectionName, pending, error, onConfirm, onCancel }: SwitchAliasDialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onCancel);
  const mono = { fontFamily: theme.font.mono };

  return createPortal(
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0, background: theme.color.overlay, zIndex: 100,
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
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 560, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.bold, color: theme.color.text, margin: 0 }}>
          Switch alias <span style={mono}>{alias}</span> here
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
          {currentTargetName === null ? (
            <>The alias does not exist yet: it will be created pointing at <strong>{collectionName}</strong>.</>
          ) : (
            <>
              The alias moves from <strong>{currentTargetName}</strong> to <strong>{collectionName}</strong>. Every
              client using it — and every key scoped to <span style={mono}>alias:{alias}</span> — follows it on the
              very next request.
            </>
          )}
        </div>
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={pending} onClick={onConfirm}>
            {pending ? "switching…" : "Switch alias here"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
