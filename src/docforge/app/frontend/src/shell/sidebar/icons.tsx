// ====== Code Summary ======
// Minimal inline-SVG line icons for the sidebar's flat nav list — plain `currentColor` strokes, no
// baked-in hex, sized to sit in a 16-18px glyph slot; the surrounding button's own text colour
// (steel at rest, forge accent when active) tints them, matching the app's existing icon pattern
// (ThemeToggle's Sun/Moon, TokenControl's KeyGlyph). Grouped in one file per the documented
// "grouped-primitives" exception to one-component-per-file (agent-memory/frontend/
// architecture-conventions.md) — each icon here is a tiny, stateless, single-purpose glyph consumed
// only by the sidebar's nav tree.

const LINE = {
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

/** Overview — a simple roof/house mark, the "step back and start here" entry. */
export function HomeGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9" />
    </svg>
  );
}

/** Collections — a folded document (echoes ForgeMark's own paper shape). */
export function CollectionsGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 4h11l4 4v12H4z" />
      <path d="M15 4v4h4" />
      <path d="M8 12h8M8 16h8" />
    </svg>
  );
}

/** Activity — a stacked queue of bars (the fleet-wide job list: jobs, failures, trends). */
export function ActivityGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  );
}

/** Fleet — a queue of two worker racks (workers, queue, capacity). */
export function FleetGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <rect x="3" y="4" width="18" height="6" rx="1" />
      <rect x="3" y="14" width="18" height="6" rx="1" />
      <circle cx="7" cy="7" r="0.6" fill="currentColor" stroke="none" />
      <circle cx="7" cy="17" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Settings — a key next to a gear-free "admin" mark (keys, audit, deployment). */
export function SettingsGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <circle cx="8" cy="8" r="4" />
      <path d="M14 14l7 7M18 14l3 3-2 2" />
    </svg>
  );
}

// ─── Collection-scope nav glyphs (the rail swaps to these while inside a collection) ───

/** Documents — a single page with text lines (the ingested corpus). */
export function DocumentsGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <rect x="5" y="3" width="14" height="18" rx="1" />
      <path d="M8 8h8M8 12h8M8 16h5" />
    </svg>
  );
}

/** Search — a magnifier (the query/hits lab). */
export function SearchGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4.3-4.3" />
    </svg>
  );
}

/** Pipelines — three chained nodes (ingestion & search editors). */
export function PipelinesGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <circle cx="5" cy="12" r="2" />
      <circle cx="12" cy="12" r="2" />
      <circle cx="19" cy="12" r="2" />
      <path d="M7 12h3M14 12h3" />
    </svg>
  );
}

/** Schema — label/value rows (the metadata contract). */
export function SchemaGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 6h4M4 12h4M4 18h4" />
      <path d="M11 6h9M11 12h9M11 18h9" />
    </svg>
  );
}

/** Back — a left chevron, the "up to the fleet" exit from a collection. */
export function BackGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M15 6l-6 6 6 6" />
    </svg>
  );
}
