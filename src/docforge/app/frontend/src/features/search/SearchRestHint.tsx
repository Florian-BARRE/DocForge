// ====== Code Summary ======
// A static (non-animated) placeholder shown before the first query runs — previews where results
// will land without implying anything is loading (that job now belongs to `SearchResultSkeleton`,
// shown only while a request is in flight).

import { theme } from "../../theme";

export function SearchRestHint() {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: theme.space.xs, padding: theme.space.xl, textAlign: "center",
        color: theme.color.dim, fontSize: theme.font.size.s,
        background: theme.color.surface, border: `1px dashed ${theme.color.line}`, borderRadius: theme.radius.l,
      }}
    >
      <span>Results will appear here.</span>
      <span>Try one of the example queries above, or type your own.</span>
    </div>
  );
}
