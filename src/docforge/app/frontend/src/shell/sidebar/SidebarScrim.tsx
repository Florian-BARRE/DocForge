// ====== Code Summary ======
// A full-viewport, click-through scrim behind the sidebar's TRANSIENT hover/focus overlay — never
// shown while pinned (a pinned rail reflows the content instead of floating over it, see
// Sidebar.tsx/App.tsx). Makes the expanded rail read as a passing flyout, not the resting state,
// closing the P0 gap where an expanded overlay could be mistaken for stuck/broken chrome.

import { theme as t } from "../../theme";

interface SidebarScrimProps {
  visible: boolean;
}

export function SidebarScrim({ visible }: SidebarScrimProps) {
  return (
    <div
      aria-hidden="true"
      data-testid="sidebar-scrim"
      style={{
        position: "fixed", inset: 0, zIndex: 499, pointerEvents: "none",
        background: t.color.overlaySubtle,
        opacity: visible ? 1 : 0,
        transition: "opacity .16s ease",
      }}
    />
  );
}
