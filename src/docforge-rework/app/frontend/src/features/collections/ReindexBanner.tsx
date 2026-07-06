// ====== Code Summary ======
// A prominent warning banner for a collection's detail page — shown whenever `needs_reindex` is
// true, whether that state predates this visit or was just set by an edit that changed the
// searchable surface (semantic/lexical/filterable flags, or the type of such a field).

import { theme } from "../../theme";

export function ReindexBanner() {
  return (
    <div
      style={{
        background: theme.color.warnSoft,
        border: `1px solid ${theme.color.warn}`,
        borderRadius: theme.radius.m,
        padding: `${theme.space.s}px ${theme.space.m}px`,
        color: theme.color.warn,
        fontSize: theme.font.size.s,
        marginBottom: theme.space.l,
      }}
    >
      Searchable schema changed — existing documents need reindexing.
    </div>
  );
}
