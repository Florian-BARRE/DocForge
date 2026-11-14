// ====== Code Summary ======
// Confirmation modal shown when a collection schema save (previewed with a dry-run PATCH) would
// DELETE fields and their stored values. Lists each removed field with its value count, the renames
// (values kept) and the fields that will need a reindex. The destructive confirm uses the error
// ink; Cancel writes nothing. The overlay shell is the shared `ConfirmDialog`.

import type { SchemaDiff } from "../../../api/collections";
import { ConfirmDialog } from "../../../components/dialog/ConfirmDialog";
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
  const removed = diff.removed ?? [];
  const renamed = diff.renamed ?? [];
  const reindex = diff.reindex_required_fields ?? [];

  return (
    <ConfirmDialog
      title="This schema change deletes stored values"
      tone="danger"
      confirmVariant="danger"
      confirmLabel="Delete values and save"
      pendingLabel="saving…"
      pending={pending}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
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
    </ConfirmDialog>
  );
}
