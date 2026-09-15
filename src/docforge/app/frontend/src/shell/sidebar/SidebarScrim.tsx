// ====== Code Summary ======
// A full-viewport scrim behind the sidebar's expanded rail, shown ONLY when the rail is a floating
// overlay rather than reflowing the content — which today is exclusively the expanded state on a
// compact/touch viewport (no room to push content there; see Sidebar.tsx's `reflow`/`isOverlay`). On
// a wide viewport expansion reflows instead — content is pushed, never floated under — so the scrim
// never shows there. Clickable when visible, so tapping outside the overlay collapses it back.

import { theme as t } from "../../theme";

interface SidebarScrimProps {
  visible: boolean;
  onClick: () => void;
}

export function SidebarScrim({ visible, onClick }: SidebarScrimProps) {
  return (
    <div
      aria-hidden="true"
      data-testid="sidebar-scrim"
      onClick={visible ? onClick : undefined}
      style={{
        position: "fixed", inset: 0, zIndex: 499, pointerEvents: visible ? "auto" : "none",
        background: t.color.overlaySubtle,
        opacity: visible ? 1 : 0,
        transition: "opacity .16s ease",
      }}
    />
  );
}
