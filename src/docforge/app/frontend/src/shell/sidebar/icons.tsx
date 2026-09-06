// ====== Code Summary ======
// Minimal inline-SVG line icons for the sidebar's section and page entries — plain `currentColor`
// strokes, no baked-in hex, sized to sit in a 16-18px glyph slot; the surrounding button's own text
// colour (steel at rest, forge accent when active) tints them, matching the app's existing icon
// pattern (TopBar's MenuGlyph, ThemeToggle's Sun/Moon, TokenControl's KeyGlyph). Grouped in one file
// per the documented "grouped-primitives" exception to one-component-per-file (agent-memory/
// frontend/architecture-conventions.md) — each icon here is a tiny, stateless, single-purpose glyph
// consumed only by the sidebar's nav tree.

const LINE = {
  fill: "none" as const,
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

/** Home — a simple roof/house mark, the "step back and start here" entry. */
export function HomeGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6 10v9a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-9" />
    </svg>
  );
}

/** Collections section — a folded document (echoes ForgeMark's own paper shape). */
export function CollectionsGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 4h11l4 4v12H4z" />
      <path d="M15 4v4h4" />
      <path d="M8 12h8M8 16h8" />
    </svg>
  );
}

/** Workers & Jobs section — two workers, one queued behind the other. */
export function WorkersGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20a6 6 0 0 1 12 0" />
      <path d="M16 5.5a3 3 0 0 1 0 5.8M18.5 20a5.5 5.5 0 0 0-3-4.9" />
    </svg>
  );
}

/** All Jobs page — a stacked queue of three bars (the fleet-wide job list, as opposed to the
 *  per-worker rack glyph below). */
export function AllJobsGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  );
}

/** Monitoring page — a small pulse/heartbeat line, job-level health rather than host metrics. */
export function MonitoringGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <path d="M3 12h4l2 7 4-14 2 7h6" />
    </svg>
  );
}

/** Admin section — a key next to a gear-free "settings" mark, reused across the API Keys page. */
export function AdminGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" {...LINE}>
      <circle cx="8" cy="8" r="4" />
      <path d="M14 14l7 7M18 14l3 3-2 2" />
    </svg>
  );
}

/** "All" — the unfiltered fleet list. */
export function AllGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

/** "Create" — new collection. */
export function CreateGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v8M8 12h8" />
    </svg>
  );
}

/** "Import" — restore a .dcexport bundle. */
export function ImportGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
      <path d="M12 3v11M8 10l4 4 4-4" />
    </svg>
  );
}

/** Workers page — a queue of two racks. */
export function WorkersPageGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <rect x="3" y="4" width="18" height="6" rx="1" />
      <rect x="3" y="14" width="18" height="6" rx="1" />
      <circle cx="7" cy="7" r="0.6" fill="currentColor" stroke="none" />
      <circle cx="7" cy="17" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** API Keys page. */
export function ApiKeyGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" {...LINE}>
      <circle cx="8" cy="14" r="3.5" />
      <path d="M10.8 11.2 20 2M16 6l3 3M13 9l2 2" />
    </svg>
  );
}

/** The collapsed rail's edge hint — a small chevron hugging its right border, hinting that
 * hovering/focusing the rail expands it. */
export function ExpandHintGlyph() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" {...LINE} strokeWidth={2.5}>
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}
