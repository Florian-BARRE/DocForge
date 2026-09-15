// ====== Code Summary ======
// The app's global navigation chrome — a persistent rail, expanded (240px) by DEFAULT. Collapsing to
// the ~72px icon rail is an EXPLICIT user toggle (SidebarFooter, persisted via useSidebarExpanded),
// never hover/focus-gated — the pre-redesign hover-to-preview behaviour hid global chrome (theme
// toggle, API token, nav) behind a transient cursor state, which is exactly the "chrome hidden behind
// hover" problem this rail fixes. On a wide viewport, expansion REFLOWS the page (App.tsx's content-
// reserving spacer widens via `onExpandedChange`) so content is pushed, never covered. On a compact/
// touch viewport (see `useSidebarCompact`) there's no room to push, so expansion stays a floating
// overlay + scrim instead (clicking the scrim collapses it back).

import { useEffect } from "react";
import { theme as t } from "../../theme";
import { useRovingTabIndex } from "../../components/useRovingTabIndex";
import { ForgeMark } from "../ForgeMark";
import type { Navigate, View } from "../view";
import { activeSidebarKey, isCollectionScopedView, SIDEBAR_PAGES, type SidebarPage } from "./sidebarConfig";
import { activeCollectionKey, collectionIdOf, COLLECTION_SIDEBAR_PAGES } from "./collectionSidebarConfig";
import { BackGlyph } from "./icons";
import { SidebarNavItem } from "./SidebarNavItem";
import { SidebarFooter } from "./SidebarFooter";
import { SidebarScrim } from "./SidebarScrim";
import { useSidebarCompact } from "./useSidebarCompact";

export const SIDEBAR_RAIL_WIDTH = 72;
export const SIDEBAR_EXPANDED_WIDTH = 240;

interface SidebarProps {
  view: View;
  onNavigate: Navigate;
  expanded: boolean;
  onToggleExpanded: () => void;
  /** Fires whenever the rail's REFLOW state changes, so a caller (App.tsx) can size a content-
   *  reserving spacer that always matches — the sole mechanism preventing overlap. */
  onExpandedChange?: (reflow: boolean) => void;
  /** Opens the root-mounted ⌘K command palette (see shell/command-palette/) — the rail only hosts
   *  the trigger affordance near the brand mark, App.tsx owns the palette's open state. */
  onOpenPalette?: () => void;
}

export function Sidebar({ view, onNavigate, expanded, onToggleExpanded, onExpandedChange, onOpenPalette }: SidebarProps) {
  const isCompact = useSidebarCompact();
  // On a wide viewport expansion pushes content (reflow); on a compact one it floats over it instead
  // (no room to push — a 240px push at 375px would shove content off the right edge).
  const reflow = expanded && !isCompact;
  const isOverlay = expanded && isCompact;

  useEffect(() => {
    onExpandedChange?.(reflow);
  }, [reflow, onExpandedChange]);

  // Scope swap: inside a specific collection the rail OWNS that collection's nav (Supabase model),
  // so there's no redundant horizontal tab strip in the content. Otherwise it shows the deployment nav.
  const collectionScoped = isCollectionScopedView(view);
  const collectionId = collectionScoped ? collectionIdOf(view) : null;
  const inCollection = collectionScoped && collectionId !== null;

  const navPages: SidebarPage[] = inCollection
    ? COLLECTION_SIDEBAR_PAGES.map((p) => ({
        key: p.key, label: p.label, icon: p.icon, view: p.build(collectionId), isActive: p.isActive,
      }))
    : SIDEBAR_PAGES;
  const activePage = inCollection ? activeCollectionKey(view) : activeSidebarKey(view);

  const roving = useRovingTabIndex(navPages.map((p) => p.key), (key) => {
    const page = navPages.find((p) => p.key === key);
    if (page) onNavigate(page.view);
  });

  return (
    <>
      <SidebarScrim visible={isOverlay} onClick={onToggleExpanded} />
      <nav
        aria-label="Global navigation"
        style={{
          position: "fixed", left: 0, top: 0, bottom: 0,
          width: expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH,
          display: "flex", flexDirection: "column",
          background: t.color.panel, borderRight: `1px solid ${t.color.line}`,
          boxShadow: isOverlay ? t.shadow.pop : "none",
          zIndex: 500, overflow: "hidden",
          transition: "width .16s cubic-bezier(0.22, 1, 0.36, 1)",
        }}
      >
        <button
          onClick={() => onNavigate({ name: "overview" })}
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

        <button
          onClick={onOpenPalette}
          title="Command palette (⌘K)"
          aria-label="Open command palette"
          style={{
            display: "flex", alignItems: "center", justifyContent: expanded ? "space-between" : "center",
            gap: t.space.s, flexShrink: 0,
            margin: expanded ? `0 ${t.space.m}px ${t.space.s}px` : `0 auto ${t.space.s}px`,
            width: expanded ? "auto" : 36, height: 30,
            background: t.color.surface2, color: t.color.dim, border: `1px solid ${t.color.line}`,
            borderRadius: t.radius.m, cursor: "pointer", padding: `0 ${t.space.s}px`,
            fontSize: t.font.size.s, fontFamily: t.font.family,
          }}
        >
          {expanded && <span>Search…</span>}
          <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs }}>⌘K</span>
        </button>

        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden", padding: `${t.space.xs}px` }}>
          {inCollection && (
            <button
              onClick={() => onNavigate({ name: "collections" })}
              title="All collections"
              style={{
                display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center",
                gap: t.space.s, width: "100%", background: "transparent", color: t.color.dim,
                border: "none", borderRadius: t.radius.m, cursor: "pointer",
                padding: t.space.s, marginBottom: t.space.xs, fontSize: t.font.size.s, fontWeight: 500,
                whiteSpace: "nowrap", textAlign: "left",
              }}
            >
              <span style={{ display: "grid", placeItems: "center", width: 22, height: 22, flexShrink: 0 }}><BackGlyph /></span>
              {expanded && <span>All collections</span>}
            </button>
          )}
          {navPages.map((page) => (
            <SidebarNavItem
              key={page.key}
              page={page}
              expanded={expanded}
              active={activePage === page.key}
              softActive={false}
              onNavigate={onNavigate}
              registerRef={roving.register}
              onItemKeyDown={roving.onKeyDown}
            />
          ))}
        </div>

        <SidebarFooter expanded={expanded} onToggleExpanded={onToggleExpanded} />
      </nav>
    </>
  );
}
