// ====== Code Summary ======
// One entry in the sidebar's flat nav list — icon + label, lit with the forge accent when it is the
// current view's HARD-active page. `softActive` (view scoped to this item without matching it
// exactly, e.g. deep inside a specific collection) gets a quiet steel/neutral lift instead — a
// "where am I" cue, never mistaken for the real active page (brand.md: forge orange marks the ONE
// active thing, never decoration). Collapsed (icon-only) shows just the glyph; expanded adds the label.

import type { KeyboardEvent } from "react";
import { theme as t } from "../../theme";
import type { Navigate } from "../view";
import type { SidebarPage } from "./sidebarConfig";

interface SidebarNavItemProps {
  page: SidebarPage;
  expanded: boolean;
  active: boolean;
  softActive: boolean;
  onNavigate: Navigate;
  registerRef: (key: string) => (el: HTMLElement | null) => void;
  onItemKeyDown: (e: KeyboardEvent, key: string) => void;
}

export function SidebarNavItem({ page, expanded, active, softActive, onNavigate, registerRef, onItemKeyDown }: SidebarNavItemProps) {
  const soft = !active && softActive;
  return (
    <button
      ref={registerRef(page.key)}
      onKeyDown={(e) => onItemKeyDown(e, page.key)}
      onClick={() => onNavigate(page.view)}
      aria-current={active ? "page" : undefined}
      title={page.label}
      style={{
        display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center",
        gap: t.space.s, width: "100%",
        background: active ? t.color.accentSoft : soft ? t.color.surface2 : "transparent",
        color: active ? t.color.accentSafe : soft ? t.color.text : t.color.dim,
        border: "none", borderRadius: t.radius.m, cursor: "pointer",
        padding: t.space.s, marginBottom: 2,
        fontSize: t.font.size.m, fontWeight: active ? 700 : 500,
        whiteSpace: "nowrap", textAlign: "left",
      }}
    >
      <span style={{ display: "grid", placeItems: "center", width: 22, height: 22, flexShrink: 0 }}>{page.icon}</span>
      {expanded && <span>{page.label}</span>}
    </button>
  );
}
