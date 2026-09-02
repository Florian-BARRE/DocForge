// ====== Code Summary ======
// A chunk's text, collapsed to ~6 lines with a toggle — most chunks are short enough to show in
// full, longer ones (structure_aware chunks composed of several blocks) get a "show more".

import { useState } from "react";
import { theme } from "../../../theme";

const COLLAPSED_LINE_CLAMP = 6;
const LONG_TEXT_THRESHOLD = 480;

export function ChunkText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.split("\n").length > COLLAPSED_LINE_CLAMP || text.length > LONG_TEXT_THRESHOLD;
  const clamp = expanded || !isLong;

  return (
    <div>
      <div
        style={{
          fontSize: theme.font.size.s, color: theme.color.text, lineHeight: 1.6, whiteSpace: "pre-wrap",
          display: clamp ? "block" : "-webkit-box",
          WebkitLineClamp: clamp ? undefined : COLLAPSED_LINE_CLAMP,
          WebkitBoxOrient: "vertical",
          overflow: clamp ? "visible" : "hidden",
        }}
      >
        {text}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: "none", border: "none", color: theme.color.accentSafe, cursor: "pointer",
            fontSize: theme.font.size.xs, fontWeight: 600, padding: 0, marginTop: 6,
          }}
        >
          {expanded ? "show less" : "show more"}
        </button>
      )}
    </div>
  );
}
