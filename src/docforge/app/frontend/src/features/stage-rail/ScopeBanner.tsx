// ====== Code Summary ======
// A one-line reminder of WHEN this pipeline runs, sat above the stage rail — steel/muted, never
// orange (this isn't the one active/primary thing on the page, it's ambient orientation for a page
// that would otherwise read as "just another settings form"). Kept local to stage-rail — the
// search-pipeline editor (edited in parallel elsewhere) gets its own, deliberately not shared.

import { theme } from "../../theme";

export function IngestScopeBanner() {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: theme.space.xs,
        color: theme.color.dim, fontSize: theme.font.size.s,
        padding: `0 0 ${theme.space.s}px`,
      }}
    >
      <span aria-hidden="true">ⓘ</span>
      Runs once when a document is ingested.
    </div>
  );
}
