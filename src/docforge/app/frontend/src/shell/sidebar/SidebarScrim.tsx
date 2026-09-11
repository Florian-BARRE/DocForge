// ====== Code Summary ======
// A full-viewport, click-through scrim behind the sidebar's expanded rail, shown ONLY when the rail
// is a floating overlay rather than reflowing the content — which today is exclusively a pin on a
// compact/touch viewport (no room to push content there; see Sidebar.tsx's `reflow`/
// `isTransientOverlay`). On a wide viewport, ANY expansion (hover, focus, or pin) reflows instead —
// content is pushed, never floated under — so the scrim never shows there. Makes an unavoidable
// overlay read as a passing flyout, not the resting state, closing the P0 gap where it could be
// mistaken for stuck/broken chrome.

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
