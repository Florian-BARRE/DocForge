// ====== Code Summary ======
// A collapsed-by-default disclosure surfacing the chunk's remaining facts that don't fit the card's
// header line — its own id, parent (hierarchical chunking), character count, located page and its
// section breadcrumb. Built on native <details>/<summary> (no JS state), mirroring
// AdvancedDisclosure's chevron pattern. Machine values (ids) are mono per brand.md; plain counts stay
// in the UI font. The breadcrumb lives here rather than beside the text because the pipeline already
// PREPENDS it to the enriched text (retrieval context) — showing it a second time up top would just
// duplicate the text's own first line.

import type { ReactNode } from "react";
import { theme } from "../../../theme";
import { displayPage } from "../format";
import { ChunkHeadingPath } from "./ChunkHeadingPath";

interface ChunkDetailsProps {
  id: string;
  parentId: string | null;
  headingPath: string[];
  charCount: number;
  blockCount: number;
  page: number | null;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: theme.space.s, fontSize: theme.font.size.s }}>
      <span style={{ color: theme.color.dim, minWidth: 110, flexShrink: 0 }}>{label}</span>
      <span style={{ color: theme.color.text, wordBreak: "break-all" }}>{children}</span>
    </div>
  );
}

export function ChunkDetails({ id, parentId, headingPath, charCount, blockCount, page }: ChunkDetailsProps) {
  return (
    <details>
      <summary
        style={{
          cursor: "pointer", userSelect: "none", listStyle: "none",
          color: theme.color.dim, fontSize: theme.font.size.xs, fontWeight: 600,
          display: "inline-flex", alignItems: "center", gap: 4,
        }}
      >
        <span className="df-chev" style={{ fontSize: theme.font.size.xs }}>▶</span>
        details
      </summary>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: theme.space.s, paddingLeft: 14 }}>
        <Row label="chunk id">
          <span style={{ fontFamily: theme.font.mono }} title={id}>{id}</span>
        </Row>
        <Row label="parent chunk">
          {parentId ? <span style={{ fontFamily: theme.font.mono }} title={parentId}>{parentId}</span> : "—"}
        </Row>
        <Row label="page">{page !== null ? `page ${displayPage(page)}` : "unlocated"}</Row>
        <Row label="characters">{charCount.toLocaleString()}</Row>
        <Row label="source blocks">{blockCount}</Row>
        {headingPath.length > 0 && (
          <Row label="section">
            <ChunkHeadingPath headingPath={headingPath} />
          </Row>
        )}
      </div>
    </details>
  );
}
