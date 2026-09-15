// ====== Code Summary ======
// The rail's bottom cluster — the always-visible account menu (theme toggle + API token control +
// deployment version) plus the explicit expand/collapse toggle. Reachable without any hover/focus:
// the sidebar is expanded by default (useSidebarExpanded), and even collapsed this footer still
// carries a compact icon-only stand-in for theme/token so both stay reachable (the compact token
// icon expands the sidebar first — this branch only renders while NOT expanded, so that's always safe).

import { theme as t } from "../../theme";
import { ThemeToggle } from "../ThemeToggle";
import { TokenControl } from "../TokenControl";
import { SidebarVersionLine } from "./SidebarVersionLine";

/** A chevron pointing the direction that toggling would expand towards. */
function CollapseGlyph({ expanded }: { expanded: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      {expanded ? <path d="M15 6l-6 6 6 6" /> : <path d="M9 6l6 6-6 6" />}
    </svg>
  );
}

interface SidebarFooterProps {
  expanded: boolean;
  onToggleExpanded: () => void;
}

export function SidebarFooter({ expanded, onToggleExpanded }: SidebarFooterProps) {
  return (
    <div style={{ flexShrink: 0, borderTop: `1px solid ${t.color.line}`, padding: t.space.s, display: "flex", flexDirection: "column", gap: t.space.s }}>
      <div
        style={{
          display: "flex", alignItems: "center",
          flexDirection: expanded ? "row" : "column",
          justifyContent: expanded ? "space-between" : "center",
          flexWrap: "wrap", gap: t.space.s,
        }}
      >
        <button
          onClick={onToggleExpanded}
          title={expanded ? "Collapse sidebar" : "Expand sidebar"}
          aria-pressed={expanded}
          style={{
            display: "grid", placeItems: "center", width: 30, height: 26, flexShrink: 0,
            border: `1px solid ${t.color.line}`, borderRadius: t.radius.s, cursor: "pointer",
            background: "transparent", color: t.color.dim,
          }}
        >
          <CollapseGlyph expanded={expanded} />
        </button>
        {expanded ? (
          <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
            <ThemeToggle />
            <TokenControl />
          </div>
        ) : (
          <>
            <ThemeToggle compact />
            <TokenControl compact onRequestExpand={onToggleExpanded} />
          </>
        )}
      </div>
      {expanded && <SidebarVersionLine />}
    </div>
  );
}
