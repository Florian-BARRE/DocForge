// ====== Code Summary ======
// One section's row in the global nav: an icon+label header — the collapsed rail's one visible
// affordance for this section — that navigates to the section's first page, plus, only once the
// sidebar is expanded, its page list underneath (each rendered by SidebarPageItem). The header
// itself stays mounted across the collapsed/expanded transition (only its label and the page list
// toggle), so a keyboard user focused on it never loses focus when the sidebar expands/collapses.
//
// Two distinct "lit" states, deliberately different in weight (brand.md: forge orange marks the
// ONE active thing, never decoration): `isSectionActive` (a HARD match — one of this section's own
// pages) gets the full forge accent; `isSectionSoftActive` (view is scoped to this section without
// matching any of its pages, e.g. deep inside a specific collection) gets a quiet steel/neutral
// lift instead — a "where am I" cue, never mistaken for the real active page.

import type { KeyboardEvent } from "react";
import { theme as t } from "../../theme";
import type { Navigate } from "../view";
import type { SidebarSection } from "./sidebarConfig";
import { SidebarPageItem } from "./SidebarPageItem";

interface SidebarSectionItemProps {
  section: SidebarSection;
  expanded: boolean;
  isSectionActive: boolean;
  isSectionSoftActive: boolean;
  activePageKey: string | null;
  onNavigate: Navigate;
  registerRef: (key: string) => (el: HTMLElement | null) => void;
  onItemKeyDown: (e: KeyboardEvent, key: string) => void;
}

export function SidebarSectionItem({
  section, expanded, isSectionActive, isSectionSoftActive, activePageKey, onNavigate, registerRef, onItemKeyDown,
}: SidebarSectionItemProps) {
  const itemKey = `section:${section.key}`;
  const softActive = !isSectionActive && isSectionSoftActive;
  return (
    <div style={{ marginTop: t.space.s }}>
      <button
        ref={registerRef(itemKey)}
        onKeyDown={(e) => onItemKeyDown(e, itemKey)}
        onClick={() => onNavigate(section.pages[0].view)}
        aria-current={!expanded && isSectionActive ? "page" : undefined}
        title={section.label}
        style={{
          display: "flex", alignItems: "center", gap: t.space.s, width: "100%",
          background: isSectionActive && !expanded ? t.color.accentSoft : softActive && !expanded ? t.color.surface2 : "transparent",
          color: isSectionActive ? t.color.accentSafe : softActive ? t.color.text : t.color.dim,
          border: "none", borderRadius: t.radius.m, cursor: "pointer",
          padding: `${t.space.s}px`,
          fontSize: t.font.size.s, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em",
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ display: "grid", placeItems: "center", width: 22, height: 22, flexShrink: 0 }}>{section.icon}</span>
        {expanded && <span>{section.label}</span>}
      </button>
      {expanded && (
        <div role="list" aria-label={`${section.label} pages`} style={{ display: "flex", flexDirection: "column", gap: 1, marginTop: 2 }}>
          {section.pages.map((page) => (
            <SidebarPageItem
              key={page.key}
              page={page}
              sectionKey={section.key}
              active={activePageKey === page.key}
              onNavigate={onNavigate}
              registerRef={registerRef}
              onItemKeyDown={onItemKeyDown}
            />
          ))}
        </div>
      )}
    </div>
  );
}
