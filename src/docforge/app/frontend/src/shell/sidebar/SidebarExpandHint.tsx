// ====== Code Summary ======
// A subtle chevron hugging the collapsed rail's right edge — hints that hovering/focusing the rail
// expands it. Rendered only while collapsed (see Sidebar.tsx); once expanded the tree itself is the
// affordance, so the hint would be redundant clutter.

import { theme as t } from "../../theme";
import { ExpandHintGlyph } from "./icons";

export function SidebarExpandHint() {
  return (
    <span
      aria-hidden="true"
      style={{
        position: "absolute", right: 4, top: "50%", transform: "translateY(-50%)",
        display: "grid", placeItems: "center", width: 12, height: 12,
        color: t.color.mute, opacity: 0.6, pointerEvents: "none",
      }}
    >
      <ExpandHintGlyph />
    </span>
  );
}
