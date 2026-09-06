// ====== Code Summary ======
// A one-line scope reminder atop the search-pipeline editor. Unlike the ingestion pipeline (runs
// once per document, async in the worker), this graph runs INLINE on every search request — a
// distinction easy to miss since both editors now look alike. Steel/muted, never the forge accent:
// per brand.md, orange is reserved for the one active/primary thing, and this is ambient context,
// not a call to action.

import { theme } from "../../theme";

export function SearchScopeBanner() {
  return (
    <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
      Runs on every search request.
    </div>
  );
}
