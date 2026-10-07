// ====== Code Summary ======
// Confirmation modal shown when a collection schema save (previewed with a dry-run PATCH) would
// DELETE fields and their stored values. Lists each removed field with its value count, the renames
// (values kept) and the fields that will need a reindex. The destructive confirm uses the error
// ink; Cancel writes nothing. Portaled to `document.body` — see DeleteCollectionDialog for why.

import { useId } from "react";
import { createPortal } from "react-dom";
import type { SchemaDiff } from "../../../api/collections";
import { Button } from "../../../components/Button";
import { useFocusTrap } from "../../../shell/useFocusTrap";
import { theme } from "../../../theme";

interface SchemaChangeConfirmDialogProps {
  diff: SchemaDiff;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ fontSize: theme.font.size.s, fontWeight: 600, color: theme.color.dim }}>{title}</div>
      <ul style={{ margin: 0, paddingLeft: theme.space.l, fontSize: theme.font.size.m, color: theme.color.text }}>{children}</ul>
    </div>
  );
}

const mono = { fontFamily: theme.font.mono } as const;

export function SchemaChangeConfirmDialog({ diff, pending, onConfirm, onCancel }: SchemaChangeConfirmDialogProps) {
  const titleId = useId();
  const panelRef = useFocusTrap<HTMLDivElement>(onCancel);
  const removed = diff.removed ?? [];
  const renamed = diff.renamed ?? [];
  const reindex = diff.reindex_required_fields ?? [];

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
          boxShadow: theme.shadow.pop, padding: theme.space.l, maxWidth: 480, width: "100%",
          display: "flex", flexDirection: "column", gap: theme.space.m,
        }}
      >
        <h2 id={titleId} style={{ fontFamily: theme.font.display, fontSize: theme.font.size.xl, fontWeight: 700, color: theme.color.text, margin: 0 }}>
          This schema change deletes stored values
        </h2>
        {removed.length > 0 && (
          <Section title="Removed fields — their values are deleted">
            {removed.map((name) => (
              <li key={name}>
                <span style={mono}>{name}</span>
                {" — "}
                <span style={{ ...mono, color: theme.color.error }}>{diff.values_lost?.[name] ?? 0}</span> stored value(s)
              </li>
            ))}
          </Section>
        )}
        {renamed.length > 0 && (
          <Section title="Renamed fields — values are kept">
            {renamed.map((r) => (
              <li key={`${r.from_name}->${r.to_name}`}>
                <span style={mono}>{r.from_name}</span> → <span style={mono}>{r.to_name}</span>
              </li>
            ))}
          </Section>
        )}
        {reindex.length > 0 && (
          <Section title="Reindex required before these are searchable">
            {reindex.map((name) => <li key={name}><span style={mono}>{name}</span></li>)}
          </Section>
        )}
        <div style={{ display: "flex", gap: theme.space.s, justifyContent: "flex-end" }}>
          <Button size="sm" disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
            {pending ? "saving…" : "Delete values and save"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
