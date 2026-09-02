// ====== Code Summary ======
// The human-readable provenance line for one search hit — the API already returns document_title/
// filename, page and heading_path, but the hit card used to hide them behind a raw doc-id/chunk-index
// mono line. This renders the citation a person actually reads (title · p.N · section path), leaving
// the id/chunk index as a secondary mono detail underneath.

import type { SearchHitModel } from "../../api/search";
import { theme } from "../../theme";
import { displayPage } from "../explorer/format";

/** Best available human label for the source document — title, else filename, else a short id. */
function documentLabel(hit: SearchHitModel): string {
  return hit.document_title || hit.filename || `document ${hit.document_id.slice(0, 8)}`;
}

export function SearchHitCitation({ hit }: { hit: SearchHitModel }) {
  const headingPath = hit.heading_path ?? [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <div
        style={{
          fontFamily: theme.font.display, fontWeight: theme.font.weight.semibold, fontSize: theme.font.size.m,
          color: theme.color.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}
        title={documentLabel(hit)}
      >
        {documentLabel(hit)}
        {hit.page != null && <span style={{ color: theme.color.dim, fontWeight: theme.font.weight.normal }}> · p.{displayPage(hit.page)}</span>}
      </div>
      {headingPath.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 4, color: theme.color.dim, fontSize: theme.font.size.xs }}>
          {headingPath.map((heading, index) => (
            <span key={index} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              {index > 0 && <span style={{ color: theme.color.mute }}>›</span>}
              <span>{heading}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
