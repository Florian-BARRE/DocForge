// ====== Code Summary ======
// The app's global navigation chrome — replaces the removed TopBar. A collapsed ~72px icon rail by
// default; hovering or focusing it TRANSIENTLY expands it into a 240px tree that OVERLAYS the
// content (`position: fixed`, content never reflows — SidebarScrim marks it as a passing flyout,
// never the resting state). Pinning (SidebarFooter) is the one path to a PERSISTENT expansion:
// pin state is owned by App.tsx (`useSidebarPin`) and passed in as props, because App also needs it
// to size its own content-reserving spacer — a PINNED rail REFLOWS the page (spacer reserves the
// full 240px) instead of floating over it, so pinning never masks content the way transient
// hover/focus overlay legitimately can. Collapsed shows one icon per section; expanded additionally
// lists each section's pages (SidebarSectionItem/SidebarPageItem). Escape collapses it back (unless
// pinned) — see onKeyDown below for the full "reliably collapses" contract (mouseleave/focus-out/Escape).

import { useState, type KeyboardEvent } from "react";
import { theme as t } from "../../theme";
import { useRovingTabIndex } from "../../components/useRovingTabIndex";
import { ForgeMark } from "../ForgeMark";
import type { Navigate, View } from "../view";
import { activePageKey, activeSectionKey, isCollectionScopedView, SIDEBAR_SECTIONS } from "./sidebarConfig";
import { SidebarSectionItem } from "./SidebarSectionItem";
import { SidebarFooter } from "./SidebarFooter";
import { SidebarScrim } from "./SidebarScrim";
import { SidebarExpandHint } from "./SidebarExpandHint";

export const SIDEBAR_RAIL_WIDTH = 72;
export const SIDEBAR_EXPANDED_WIDTH = 240;

interface SidebarProps {
  view: View;
  onNavigate: Navigate;
  pinned: boolean;
  onTogglePin: () => void;
}

/** Every currently-navigable item key, in tree order — section headers always, pages only once expanded. */
function navigationOrder(expanded: boolean): string[] {
  return SIDEBAR_SECTIONS.flatMap((section) => [
    `section:${section.key}`,
    ...(expanded ? section.pages.map((page) => `page:${section.key}:${page.key}`) : []),
  ]);
}

export function Sidebar({ view, onNavigate, pinned, onTogglePin }: SidebarProps) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const expanded = pinned || hovered || focused;
  // Only a transient (unpinned) expansion is an overlay that needs a scrim/heavier shadow — a
  // pinned rail already reflowed the page, so it reads as permanent chrome, not a flyout.
  const isTransientOverlay = expanded && !pinned;

  const activeSection = activeSectionKey(view);
  const activePage = activePageKey(view);
  const collectionScoped = isCollectionScopedView(view);

  const roving = useRovingTabIndex(navigationOrder(expanded), (key) => {
    const [kind, sectionKey, pageKey] = key.split(":");
    const section = SIDEBAR_SECTIONS.find((s) => s.key === sectionKey);
    if (!section) return;
    const target = kind === "page" ? section.pages.find((p) => p.key === pageKey) : section.pages[0];
    if (target) onNavigate(target.view);
  });

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || pinned) return;
    (document.activeElement as HTMLElement | null)?.blur();
    setHovered(false);
    setFocused(false);
  };

  return (
    <>
      <SidebarScrim visible={isTransientOverlay} />
      <nav
        aria-label="Global navigation"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setFocused(true)}
        onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setFocused(false); }}
        onKeyDown={onKeyDown}
        style={{
          position: "fixed", left: 0, top: 0, bottom: 0,
          width: expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH,
          display: "flex", flexDirection: "column",
          background: t.color.panel, borderRight: `1px solid ${t.color.line}`,
          boxShadow: isTransientOverlay ? t.shadow.pop : "none",
          zIndex: 500, overflow: "hidden",
          transition: "width .16s cubic-bezier(0.22, 1, 0.36, 1)",
        }}
      >
        <button
          onClick={() => onNavigate({ name: "home" })}
          title="DocForge home"
          style={{
            display: "flex", alignItems: "center", gap: t.space.s, flexShrink: 0,
            background: "none", border: "none", cursor: "pointer", textAlign: "left",
            padding: t.space.m, height: 58,
          }}
        >
          <ForgeMark size={30} animated={false} />
          {expanded && (
            <span style={{ fontFamily: t.font.display, fontWeight: 800, fontSize: t.font.size.xl, letterSpacing: "-0.035em", color: t.color.text, whiteSpace: "nowrap" }}>
              Doc<span style={{ color: t.color.accentSafe }}>Forge</span>
            </span>
          )}
        </button>

        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden", padding: `0 ${t.space.xs}px` }}>
          {SIDEBAR_SECTIONS.map((section) => (
            <SidebarSectionItem
              key={section.key}
              section={section}
              expanded={expanded}
              isSectionActive={activeSection === section.key}
              isSectionSoftActive={section.key === "collections" && collectionScoped}
              activePageKey={activePage}
              onNavigate={onNavigate}
              registerRef={roving.register}
              onItemKeyDown={roving.onKeyDown}
            />
          ))}
        </div>

        {!expanded && <SidebarExpandHint />}
        <SidebarFooter expanded={expanded} pinned={pinned} onTogglePin={onTogglePin} />
      </nav>
    </>
  );
}
