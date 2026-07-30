// ====== Code Summary ======
// One search hit: its score (as a premium ember badge), the chunk text (reusing the explorer's
// truncatable ChunkText), and a small mono meta line (short document id, chunk index, token count).

import { useState } from "react";
import type { SearchHitModel } from "../../api/search";
import { ChunkText } from "../explorer/chunks/ChunkText";
import { theme } from "../../theme";

interface SearchHitCardProps {
  hit: SearchHitModel;
}

export function SearchHitCard({ hit }: SearchHitCardProps) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.surface, border: `1px solid ${hover ? theme.color.accentLine : theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
        boxShadow: hover ? theme.shadow.md : theme.shadow.sm,
        transform: hover ? "translateY(-1px)" : "none",
        transition: "transform .15s ease, box-shadow .15s ease, border-color .15s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <strong
          style={{
            fontFamily: theme.font.mono, fontSize: theme.font.size.m, fontWeight: 700,
            color: theme.color.accent, background: theme.color.accentSoft,
            borderRadius: theme.radius.pill, padding: "2px 10px",
          }}
        >
          {hit.score.toFixed(4)}
        </strong>
        <span style={{ marginLeft: "auto", fontFamily: theme.font.mono, fontSize: theme.font.size.xs, color: theme.color.dim }}>
          doc {hit.document_id.slice(0, 8)} · chunk #{hit.chunk_index} · {hit.token_count} tokens
        </span>
      </div>
      <ChunkText text={hit.text} />
    </div>
  );
}
