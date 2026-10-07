// ====== Code Summary ======
// The structured config diff — one row per changed path (path + op + before → after). Paths and
// values are machine values, so they render in JetBrains Mono; secrets arrive already masked.

import type { ConfigDiffEntry } from "../../../api/configVersions";
import { theme } from "../../../theme";

const OP_COLOR: Record<ConfigDiffEntry["op"], string> = {
  added: theme.color.ok,
  removed: theme.color.error,
  changed: theme.color.warn,
};

/** Compact one-line JSON for a diff value (absent → an em dash). */
function show(value: unknown): string {
  if (value === undefined || value === null) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

const mono = { fontFamily: theme.font.mono, fontSize: theme.font.size.s, wordBreak: "break-all" } as const;

export function ConfigDiffView({ changes }: { changes: ConfigDiffEntry[] }) {
  if (changes.length === 0) {
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.m }}>No differences.</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, maxHeight: 360, overflowY: "auto" }}>
      {changes.map((c) => (
        <div
          key={`${c.op}:${c.path}`}
          style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: theme.space.s, padding: theme.space.xs, borderBottom: `1px solid ${theme.color.line}` }}
        >
          <span style={{ color: OP_COLOR[c.op], fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold }}>{c.op}</span>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ ...mono, color: theme.color.text }}>{c.path}</span>
            <span style={{ ...mono, color: theme.color.dim }}>
              {show(c.before)} → {show(c.after)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
