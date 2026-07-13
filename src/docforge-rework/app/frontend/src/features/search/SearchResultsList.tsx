// ====== Code Summary ======
// The results section: echoed effective query + hit count, the late-interaction-skipped notice
// when present, and the ranked hit list itself.

import type { SearchResponse } from "../../api/search";
import { theme } from "../../theme";
import { LateInteractionSkippedNotice } from "./LateInteractionSkippedNotice";
import { SearchHitCard } from "./SearchHitCard";

interface SearchResultsListProps {
  response: SearchResponse;
}

export function SearchResultsList({ response }: SearchResultsListProps) {
  const skipped = response.debug_info?.late_interaction_skipped;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>
        {response.hits.length} result{response.hits.length === 1 ? "" : "s"} for <em>{response.query}</em>
      </div>

      {typeof skipped === "string" && <LateInteractionSkippedNotice reason={skipped} />}

      {response.hits.length === 0 && (
        <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No matches.</div>
      )}

      {response.hits.map((hit) => (
        <SearchHitCard key={hit.chunk_id} hit={hit} />
      ))}
    </div>
  );
}
