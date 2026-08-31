// ====== Code Summary ======
// A chunk's section breadcrumb (outer→inner headings) — the same context the pipeline already
// prepends to the embedded text, shown here as its own quiet structured line so it stays legible
// even once the text is truncated or the heading scrolls out of the collapsed preview.

import { theme } from "../../../theme";

export function ChunkHeadingPath({ headingPath }: { headingPath: string[] }) {
  if (!headingPath.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 4, color: theme.color.dim, fontSize: theme.font.size.xs }}>
      {headingPath.map((heading, index) => (
        <span key={index} style={{ display: "flex", alignItems: "center", gap: 4 }}>
          {index > 0 && <span style={{ color: theme.color.mute }}>›</span>}
          <span>{heading}</span>
        </span>
      ))}
    </div>
  );
}
