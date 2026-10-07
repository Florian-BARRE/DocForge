// ====== Code Summary ======
// Modal confirm for restoring a config version — shows the diff from the CURRENT head to the target
// version (what the restore will change) and requires an explicit confirm. Restoring always writes a
// NEW version. Portaled to document.body for the same `df-rise` reason as DeleteCollectionDialog.

import { useId } from "react";
import { createPortal } from "react-dom";
import type { ConfigDiffEntry } from "../../../api/configVersions";
import { Button } from "../../../components/Button";
import { useFocusTrap } from "../../../shell/useFocusTrap";
import { theme } from "../../../theme";
import { ConfigDiffView } from "./ConfigDiffView";

interface RestoreVersionDialogProps {
  version: number;
  head: number;
  changes: ConfigDiffEntry[] | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RestoreVersionDialog({ version, head, changes, pending, error, onConfirm, onCancel }: RestoreVersionDialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onCancel);

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
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 720, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: theme.font.weight.bold, color: theme.color.text, margin: 0 }}>
          Restore version <span style={{ fontFamily: theme.font.mono }}>v{version}</span>
        </h2>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.m, lineHeight: 1.5 }}>
          Changes from the current <span style={{ fontFamily: theme.font.mono }}>v{head}</span>. The restore
          writes a new version; current provider keys at the same endpoint are kept.
        </div>
        {changes === null ? (
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.m }}>loading diff…</div>
        ) : (
          <ConfigDiffView changes={changes} />
        )}
        {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="primary" size="sm" disabled={pending || changes === null} onClick={onConfirm}>
            {pending ? "restoring…" : `Restore v${version}`}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
