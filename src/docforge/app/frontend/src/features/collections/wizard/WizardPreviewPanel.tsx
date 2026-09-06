// ====== Code Summary ======
// Live JSON preview of the collection contract the wizard is currently building — sits beside the
// Identity/Schema steps so the (fairly narrow) form card no longer leaves most of the page blank.
// Read-only: reuses the same surface-2/mono "JSON view" look as JsonField/SchemaForm's own JSON
// escape hatch, but this one only ever displays — editing happens through the actual form fields.

import { theme } from "../../../theme";

interface WizardPreviewPanelProps {
  payload: unknown;
}

export function WizardPreviewPanel({ payload }: WizardPreviewPanelProps) {
  return (
    <div
      style={{
        flex: "1 1 360px", minWidth: 320, alignSelf: "flex-start", position: "sticky", top: theme.space.xl,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, boxShadow: theme.shadow.sm,
        display: "flex", flexDirection: "column",
      }}
    >
      <div style={{ padding: `${theme.space.m}px ${theme.space.l}px`, borderBottom: `1px solid ${theme.color.line}` }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l, color: theme.color.text }}>
          Live preview
        </span>
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, marginTop: 2 }}>
          The contract this wizard will submit, updated as you fill the form in.
        </div>
      </div>
      <pre
        style={{
          margin: 0, padding: theme.space.l, background: theme.color.surface2,
          color: theme.color.text, fontFamily: theme.font.mono, fontSize: theme.font.size.s,
          overflow: "auto", maxHeight: 560,
          borderBottomLeftRadius: theme.radius.l, borderBottomRightRadius: theme.radius.l,
        }}
      >
        {JSON.stringify(payload, null, 2)}
      </pre>
    </div>
  );
}
