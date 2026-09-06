// ====== Code Summary ======
// One page link inside an expanded section's tree — icon + label, indented under its section
// header, lit with the forge accent when it is the current view's active page. Only mounted while
// the sidebar is expanded (see SidebarSectionItem) — a collapsed rail shows section icons only.

import type { KeyboardEvent } from "react";
import { theme as t } from "../../theme";
import type { Navigate } from "../view";
import type { SidebarPage } from "./sidebarConfig";

interface SidebarPageItemProps {
  page: SidebarPage;
  sectionKey: string;
  active: boolean;
  onNavigate: Navigate;
  registerRef: (key: string) => (el: HTMLElement | null) => void;
  onItemKeyDown: (e: KeyboardEvent, key: string) => void;
}

export function SidebarPageItem({ page, sectionKey, active, onNavigate, registerRef, onItemKeyDown }: SidebarPageItemProps) {
  const itemKey = `page:${sectionKey}:${page.key}`;
  return (
    <button
      ref={registerRef(itemKey)}
      onKeyDown={(e) => onItemKeyDown(e, itemKey)}
      onClick={() => onNavigate(page.view)}
      aria-current={active ? "page" : undefined}
      style={{
        display: "flex", alignItems: "center", gap: t.space.s, width: "100%",
        background: active ? t.color.accentSoft : "transparent",
        color: active ? t.color.accentSafe : t.color.text,
        border: "none", borderRadius: t.radius.m, cursor: "pointer",
        padding: `${t.space.s}px ${t.space.s}px ${t.space.s}px ${t.space.xl}px`,
        fontSize: t.font.size.m, fontWeight: active ? 700 : 500,
        whiteSpace: "nowrap", textAlign: "left",
      }}
    >
      <span style={{ display: "grid", placeItems: "center", width: 16, height: 16, flexShrink: 0 }}>{page.icon}</span>
      <span>{page.label}</span>
    </button>
  );
}
