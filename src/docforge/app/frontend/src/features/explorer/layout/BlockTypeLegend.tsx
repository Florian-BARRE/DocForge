// ====== Code Summary ======
// The colour key for the Layout view — one swatch + label per structural block role, so the coloured
// boxes drawn on each page render are legible at a glance.

import { theme } from "../../../theme";
import { BLOCK_LEGEND } from "./blockColors";

export function BlockTypeLegend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m, alignItems: "center" }}>
      <span style={{ fontSize: theme.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em", color: theme.color.dim }}>
        Block types
      </span>
      {BLOCK_LEGEND.map((entry) => (
        <span key={entry.label} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span
            aria-hidden
            style={{ width: 12, height: 12, borderRadius: 3, border: `2px solid ${entry.color}`, background: "transparent" }}
          />
          <span style={{ fontSize: theme.font.size.xs, color: theme.color.dim }}>{entry.label}</span>
        </span>
      ))}
    </div>
  );
}
