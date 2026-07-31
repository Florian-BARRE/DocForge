// ====== Code Summary ======
// The results section: echoed effective query + hit count and the ranked hit list itself.

import type { SearchResponse } from "../../api/search";
import { theme } from "../../theme";
import { SearchHitCard } from "./SearchHitCard";

interface SearchResultsListProps {
  response: SearchResponse;
}

export function SearchResultsList({ response }: SearchResultsListProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        <strong style={{ color: theme.color.text }}>{response.hits.length}</strong> result{response.hits.length === 1 ? "" : "s"} for{" "}
        <em style={{ color: theme.color.text, fontStyle: "normal", fontWeight: 600 }}>“{response.query}”</em>
      </div>

      {response.hits.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, padding: theme.space.l, textAlign: "center" }}>
          No matches.
        </div>
      )}

      {response.hits.map((hit) => (
        <SearchHitCard key={hit.chunk_id} hit={hit} />
      ))}
    </div>
  );
}
