// ====== Code Summary ======
// The rail's bottom cluster — rehomed from TopBar's right-hand controls. The pin toggle is always
// visible (meaningful even collapsed: it is what keeps the sidebar open without hovering). The full
// ThemeToggle segmented control and TokenControl's inline "paste token" editor both need more width
// than the ~72px collapsed rail has to offer, so they only mount once expanded — but collapsed still
// gets a COMPACT icon-only stand-in for each, so both stay reachable without first triggering a full
// hover/focus expansion: the compact theme icon toggles directly (no extra width needed), the
// compact token icon pins the sidebar open (safe — this branch only renders while NOT expanded, so
// pinned is always false here) so the real editor becomes reachable in its full, reflowed form.

import { theme as t } from "../../theme";
import { ThemeToggle } from "../ThemeToggle";
import { TokenControl } from "../TokenControl";

function PinGlyph({ pinned }: { pinned: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={pinned ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2v7M8 9h8l2 6H6z M12 15v7" />
    </svg>
  );
}

interface SidebarFooterProps {
  expanded: boolean;
  pinned: boolean;
  onTogglePin: () => void;
}

export function SidebarFooter({ expanded, pinned, onTogglePin }: SidebarFooterProps) {
  return (
    <div
      style={{
        flexShrink: 0, borderTop: `1px solid ${t.color.line}`, padding: t.space.s,
        display: "flex", alignItems: "center",
        flexDirection: expanded ? "row" : "column",
        justifyContent: expanded ? "space-between" : "center",
        flexWrap: "wrap", gap: t.space.s,
      }}
    >
      <button
        onClick={onTogglePin}
        title={pinned ? "Unpin sidebar" : "Pin sidebar open"}
        aria-pressed={pinned}
        style={{
          display: "grid", placeItems: "center", width: 30, height: 26, flexShrink: 0,
          border: `1px solid ${t.color.line}`, borderRadius: t.radius.s, cursor: "pointer",
          background: pinned ? t.color.accentSoft : "transparent",
          color: pinned ? t.color.accentSafe : t.color.dim,
        }}
      >
        <PinGlyph pinned={pinned} />
      </button>
      {expanded ? (
        <div style={{ display: "flex", alignItems: "center", gap: t.space.s, flexWrap: "wrap" }}>
          <ThemeToggle />
          <TokenControl />
        </div>
      ) : (
        <>
          <ThemeToggle compact />
          <TokenControl compact onRequestExpand={onTogglePin} />
        </>
      )}
    </div>
  );
}
