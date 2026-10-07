// ====== Code Summary ======
// A calm notice rendered above the results when the backend attached filter hints (a filter value
// no document stores). One line per hint: the message plus clickable suggestion chips that re-run
// the search with that value substituted. Uses the warn ink — not error red, not forge orange.

import type { SearchHint } from "../../api/search";
import { theme } from "../../theme";

interface SearchHintsNoticeProps {
  hints: SearchHint[];
  onPickSuggestion: (hint: SearchHint, suggestion: string) => void;
}

export function SearchHintsNotice({ hints, onPickSuggestion }: SearchHintsNoticeProps) {
  if (hints.length === 0) return null;
  return (
    <div
      role="status"
      style={{
        background: theme.color.warnSoft, borderLeft: `3px solid ${theme.color.warn}`, borderRadius: theme.radius.s,
        padding: `${theme.space.s}px ${theme.space.m}px`, marginBottom: theme.space.m,
        display: "flex", flexDirection: "column", gap: theme.space.s, fontSize: theme.font.size.m, color: theme.color.text,
      }}
    >
      {hints.map((hint, index) => (
        <div key={`${hint.field}-${index}`} style={{ display: "flex", alignItems: "center", gap: theme.space.s, flexWrap: "wrap" }}>
          <span>{hint.message}</span>
          {(hint.suggestions ?? []).map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onPickSuggestion(hint, suggestion)}
              style={{
                background: theme.color.surface, color: theme.color.warnStrong, border: `1px solid ${theme.color.warn}`,
                borderRadius: theme.radius.s, padding: `2px ${theme.space.s}px`, cursor: "pointer",
                fontFamily: theme.font.family, fontSize: theme.font.size.s,
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}
