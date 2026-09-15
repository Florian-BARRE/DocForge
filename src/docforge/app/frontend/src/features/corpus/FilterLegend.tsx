// ====== Code Summary ======
// Compact legend explaining the corpus grid's three search-nature badges (filter/dense/bm25) —
// shown once at the top of CorpusFilterPanel so a reader knows what those tiny header badges mean
// before scanning the grouped filter controls below. Renders from the same COLUMN_NATURE_BADGES
// source ColumnNatureBadges uses, so label/tone/description can never drift between the two.

import { theme } from "../../theme";
import { COLUMN_NATURE_BADGES, type ColumnNatureKey } from "./columns/columnNature";

const NATURE_ORDER: ColumnNatureKey[] = ["filterable", "semantic", "lexical"];

export function FilterLegend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.l, fontSize: theme.font.size.xs, color: theme.color.dim }}>
      {NATURE_ORDER.map((key) => {
        const badge = COLUMN_NATURE_BADGES[key];
        return (
          <span key={key} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontFamily: theme.font.mono, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.medium,
                color: badge.fg, background: badge.bg, borderRadius: theme.radius.s, padding: "0 4px", lineHeight: "14px",
              }}
            >
              {badge.label}
            </span>
            {badge.description}
          </span>
        );
      })}
    </div>
  );
}
