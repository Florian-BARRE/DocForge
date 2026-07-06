// ====== Code Summary ======
// Renders one metadata value according to its runtime shape — the same value can be a scalar, a
// boolean, a short tag list or a long generated sentence list, and each gets its own compact
// look. Shared by the document facts table and the chunk metadata block.

import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";

const SHORT_TAG_MAX_LENGTH = 24;

export function ValueRenderer({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === "")
    return <span style={{ color: theme.color.dim }}>—</span>;

  if (typeof value === "boolean")
    return <span style={{ color: value ? theme.color.ok : theme.color.dim }}>{value ? "✓" : "–"}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span style={{ color: theme.color.dim }}>—</span>;
    const isShortTags = value.every((v) => typeof v !== "object" && String(v).length <= SHORT_TAG_MAX_LENGTH);
    if (isShortTags)
      return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {value.map((v, i) => <Chip key={i} tone="dim">{String(v)}</Chip>)}
        </div>
      );
    return (
      <ul style={{ margin: 0, paddingLeft: theme.space.m, display: "flex", flexDirection: "column", gap: 2 }}>
        {value.map((v, i) => (
          <li key={i} style={{ fontSize: theme.font.size.s }}>{typeof v === "object" ? JSON.stringify(v) : String(v)}</li>
        ))}
      </ul>
    );
  }

  if (typeof value === "object")
    return <code style={{ fontFamily: theme.font.mono, fontSize: theme.font.size.xs }}>{JSON.stringify(value)}</code>;

  return <span>{String(value)}</span>;
}
