// ====== Code Summary ======
// The header's compact second line — tiny mono badges naming a column's search nature (filterable/
// semantic/lexical), so a reader can tell at a glance whether sorting/filtering or a search query
// actually reaches this field, without opening the filter panel. Renders nothing when a column has
// none of the three flags (most base columns only carry `filterable`; only metadata columns can
// carry `semantic`/`lexical`). Shares its copy/tone with CorpusFilterPanel's legend via
// columns/columnNature.ts so the two surfaces can't drift apart.

import { theme } from "../../theme";
import { COLUMN_NATURE_BADGES, type ColumnNatureKey } from "./columns/columnNature";

interface ColumnNatureBadgesProps {
  filterable?: boolean;
  semantic?: boolean;
  lexical?: boolean;
}

export function ColumnNatureBadges({ filterable, semantic, lexical }: ColumnNatureBadgesProps) {
  const flags: Record<ColumnNatureKey, boolean | undefined> = { filterable, semantic, lexical };
  const active = (Object.keys(flags) as ColumnNatureKey[]).filter((key) => flags[key]);
  if (active.length === 0) return null;

  return (
    <div style={{ display: "flex", gap: 3, marginTop: 3 }}>
      {active.map((key) => {
        const badge = COLUMN_NATURE_BADGES[key];
        return (
          <span
            key={key}
            title={badge.description}
            style={{
              fontFamily: theme.font.mono, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.medium,
              // Override the header cell's own uppercase/tracking so these short machine words
              // (filter/dense/bm25) render as-is, matching every other mono machine value in the UI.
              textTransform: "none", letterSpacing: "normal",
              color: badge.fg, background: badge.bg,
              borderRadius: theme.radius.s, padding: "0 4px", lineHeight: "14px",
            }}
          >
            {badge.label}
          </span>
        );
      })}
    </div>
  );
}
