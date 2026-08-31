// ====== Code Summary ======
// Renders one document-metadata value inside a grid cell, switching on runtime shape rather than
// declared field type (same philosophy as the explorer's ValueRenderer, reimplemented locally —
// feature slices never cross-import — since this grid's rendering budget is much tighter: no
// bullet lists, just a compact single-line summary per cell).

import { theme } from "../../theme";

export function MetadataValueCell({ value }: { value: unknown }) {
  const dash = <span style={{ color: theme.color.mute }}>—</span>;

  if (value === null || value === undefined || value === "") return dash;

  if (typeof value === "boolean")
    return value ? <span style={{ color: theme.color.ok }}>✓</span> : dash;

  if (Array.isArray(value))
    return value.length === 0
      ? dash
      : <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim }} title={value.map(String).join(", ")}>{value.map(String).join(", ")}</span>;

  if (typeof value === "object")
    return <span style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>{JSON.stringify(value)}</span>;

  const text = String(value);
  return (
    <span
      title={text}
      style={{
        fontSize: theme.font.size.s, color: theme.color.text, display: "block",
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 220,
      }}
    >
      {text}
    </span>
  );
}
