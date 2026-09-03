// ====== Code Summary ======
// One row inside an `OverflowMenu` popover — a full-width, hover-tinted button. `tone="danger"`
// renders it in the error ink for destructive actions (delete, remove…), matching `Button`'s own
// danger variant so a destructive menu item reads consistently with a destructive standalone button.

import { useState, type ReactNode } from "react";
import { theme as t } from "../theme";

interface OverflowMenuItemProps {
  onClick: () => void;
  tone?: "default" | "danger";
  children: ReactNode;
}

export function OverflowMenuItem({ onClick, tone = "default", children }: OverflowMenuItemProps) {
  const [hover, setHover] = useState(false);

  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex", alignItems: "center", width: "100%", textAlign: "left",
        background: hover ? (tone === "danger" ? t.color.errorSoft : t.color.surface2) : "transparent",
        color: tone === "danger" ? t.color.error : t.color.text,
        border: "none", borderRadius: t.radius.s,
        padding: `${t.space.s}px ${t.space.m}px`,
        fontSize: t.font.size.m, fontWeight: t.font.weight.medium, cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
