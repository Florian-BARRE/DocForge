// ====== Code Summary ======
// One search hit: its score, the chunk text (reusing the explorer's truncatable ChunkText), and a
// small meta line (short document id, chunk index, token count).

import type { SearchHitModel } from "../../api/search";
import { ChunkText } from "../explorer/chunks/ChunkText";
import { theme } from "../../theme";

interface SearchHitCardProps {
  hit: SearchHitModel;
}

export function SearchHitCard({ hit }: SearchHitCardProps) {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.card, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, padding: theme.space.m,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong style={{ fontSize: theme.font.size.m, color: theme.color.accent }}>{hit.score.toFixed(4)}</strong>
        <span style={{ marginLeft: "auto", fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          doc {hit.document_id.slice(0, 8)} · chunk #{hit.chunk_index} · {hit.token_count} tokens
        </span>
      </div>
      <ChunkText text={hit.text} />
    </div>
  );
}
