// ====== Code Summary ======
// The LOADING placeholder — shaped like the real hit-card list, pulsing, shown ONLY while a search
// request is in flight (see `SearchLabPage`). It previously rendered at rest instead, which read as
// a permanently-stuck loader; the resting-state preview now lives in `SearchRestHint` instead. Same
// `df-pulse` keyframe idiom as `ProviderHealthBoard`'s skeleton, kept local (no shared CSS file entry
// exists for it yet) rather than introducing a third copy under a different name.

import { theme } from "../../theme";

const BAR_WIDTHS = ["78%", "94%", "58%"];

function skeletonCard(key: string, delay: number) {
  return (
    <div
      key={key}
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        background: theme.color.surface, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, padding: theme.space.m,
        animation: "df-search-pulse 1.4s ease-in-out infinite", animationDelay: `${delay}s`,
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

/** Loading placeholder shown while a search request is in flight — never at rest. */
export function SearchResultSkeleton() {
  return (
    <div role="status" aria-label="Searching…" style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      {skeletonCard("skeleton-1", 0)}
      {skeletonCard("skeleton-2", 0.15)}
      <style>
        {"@keyframes df-search-pulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } } "
          + "@media (prefers-reduced-motion: reduce) { [style*=\"df-search-pulse\"] { animation: none !important; } }"}
      </style>
    </div>
  );
}
