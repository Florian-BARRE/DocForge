// ====== Code Summary ======
// The app's global navigation chrome — replaces the removed TopBar. A collapsed ~72px icon rail by
// default; hovering or focusing it expands it into a 240px tree — on a wide, hover-capable viewport
// only (see `useSidebarCompact`), since a compact/touch viewport has no meaningful hover state and
// would otherwise "open" unannounced from a resting cursor/finger. Regardless of WHY it expands
// (hover, focus, or a PERSISTENT pin), on a wide viewport App.tsx is told via `onExpandedChange` so
// its content-reserving spacer always REFLOWS to match the rail's actual rendered width — content is
// pushed, never partially covered (a fixed-position overlay wider than the spacer used to clip
// content: the iteration-2 regression for pin-at-rest, and again for hover/focus since landing on a
// top-level route via a sidebar click leaves the cursor resting inside the rail — not a brief
// preview but the steady state). Only a compact-viewport pin stays a non-reflowing overlay+scrim
// (no room to push there). Pinning (SidebarFooter) is the one way to expand on a compact viewport
// (pin state is owned by App.tsx via `useSidebarPin`, passed in as props) — it is always reachable,
// even collapsed, so a small screen still has a visible way to open the tree. Collapsed shows one
// icon per section; expanded additionally lists each section's pages (SidebarSectionItem/
// SidebarPageItem). Escape collapses it back (unless pinned) — see onKeyDown below for the full
// "reliably collapses" contract (mouseleave/focus-out/Escape).

import { useEffect, useState, type KeyboardEvent } from "react";
import { theme as t } from "../../theme";
import { useRovingTabIndex } from "../../components/useRovingTabIndex";
import { ForgeMark } from "../ForgeMark";
import type { Navigate, View } from "../view";
import { activePageKey, activeSectionKey, isCollectionScopedView, SIDEBAR_SECTIONS } from "./sidebarConfig";
import { SidebarSectionItem } from "./SidebarSectionItem";
import { SidebarFooter } from "./SidebarFooter";
import { SidebarScrim } from "./SidebarScrim";
import { SidebarExpandHint } from "./SidebarExpandHint";
import { useSidebarCompact } from "./useSidebarCompact";

export const SIDEBAR_RAIL_WIDTH = 72;
export const SIDEBAR_EXPANDED_WIDTH = 240;

interface SidebarProps {
  view: View;
  onNavigate: Navigate;
  pinned: boolean;
  onTogglePin: () => void;
  /** Fires whenever the rendered expansion state changes, so a caller (App.tsx) can size a
   *  content-reserving spacer that always matches — the sole mechanism preventing overlap. */
  onExpandedChange?: (expanded: boolean) => void;
}

/** Every currently-navigable item key, in tree order — section headers always, pages only once expanded. */
function navigationOrder(expanded: boolean): string[] {
  return SIDEBAR_SECTIONS.flatMap((section) => [
    `section:${section.key}`,
    ...(expanded ? section.pages.map((page) => `page:${section.key}:${page.key}`) : []),
  ]);
}

export function Sidebar({ view, onNavigate, pinned, onTogglePin, onExpandedChange }: SidebarProps) {
  const isCompact = useSidebarCompact();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  // Hover/focus only drive expansion on a wide, hover-capable viewport — on a compact one the pin
  // toggle is the only way in, so it never opens from a resting cursor/finger.
  const expanded = pinned || (!isCompact && (hovered || focused));
  // ANY expansion REFLOWS the page on a wide viewport — hover/focus preview included, not just a
  // persistent pin. A `position: fixed` rail that renders wider than the content's reserved offset
  // clips the page underneath it (measured regression: h1 left=180 while the hovered rail occupied
  // 0-240 — landing on a top-level route by clicking a sidebar link leaves the cursor resting
  // INSIDE the rail, so the "transient" hover overlay was in practice the steady state, not brief).
  // On a compact viewport (narrow and/or touch — see `useSidebarCompact`) there's no room to push:
  // hover/focus never expand there in the first place (see `expanded` above), and a 240px push from
  // pinning would shove content off the right edge instead (the iteration-3 FIX-B regression:
  // pinning at 375px clipped content) — so pinning stays an OVERLAY+scrim there.
  const reflow = expanded && !isCompact;
  const isTransientOverlay = expanded && !reflow;

  // Report the REFLOW state to the caller's content-reserving spacer (App.tsx) so it always matches
  // the rail's actual rendered width on a wide viewport — content is pushed, never partially
  // covered. Only a compact-viewport pin stays an overlay (no room to push there).
  useEffect(() => {
    onExpandedChange?.(reflow);
  }, [reflow, onExpandedChange]);

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
