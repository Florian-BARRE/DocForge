// ====== Code Summary ======
// A subtle placeholder shaped like the real hit-card list — rendered instead of a bare void before
// the first query runs, so the resting state previews the layout that's about to fill in. Never
// animates or uses the accent (nothing is actually loading yet — this is a preview, not a spinner).

import { theme } from "../../theme";

const BAR_WIDTHS = ["78%", "94%", "58%"];

function skeletonCard(key: string) {
  return (
    <div
      key={key}
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ width: 52, height: 18, borderRadius: theme.radius.pill, background: theme.color.surface2 }} />
        <span style={{ width: "40%", height: 14, borderRadius: theme.radius.s, background: theme.color.surface2 }} />
      </div>
      {BAR_WIDTHS.map((width) => (
        <span key={width} style={{ width, height: 10, borderRadius: theme.radius.s, background: theme.color.surface2 }} />
      ))}
    </div>
  );
}

export function SearchResultSkeleton() {
  return (
    <div aria-hidden style={{ display: "flex", flexDirection: "column", gap: theme.space.s, opacity: 0.7 }}>
      {skeletonCard("skeleton-1")}
      {skeletonCard("skeleton-2")}
    </div>
  );
}
