// ====== Code Summary ======
// The composition root: owns the current View, provides the one navigate function (NavigateProvider)
// and renders the page the route table (routes.tsx) maps the View to. Hand-rolled routing (no
// router dependency) — a plain useState<View> is enough for this app's depth.

import { useCallback, useState } from "react";
import { CommandPalette } from "./shell/command-palette/CommandPalette";
import { useCommandPaletteHotkey } from "./shell/command-palette/useCommandPaletteHotkey";
import { ErrorBoundary } from "./shell/ErrorBoundary";
import { NavigateProvider } from "./shell/navigation";
import { Sidebar, SIDEBAR_EXPANDED_WIDTH, SIDEBAR_RAIL_WIDTH } from "./shell/sidebar/Sidebar";
import { useSidebarExpanded } from "./shell/sidebar/useSidebarExpanded";
import { ToastProvider } from "./shell/toast";
import { parseViewFromHash } from "./shell/urlSync";
import { useUrlSync } from "./shell/useUrlSync";
import type { View } from "./shell/view";
import { renderRoute } from "./routes";
import { theme } from "./theme";

export function App() {
  // Bootstrap from the current URL hash so a refresh or a shared link restores the same view.
  const [view, setView] = useState<View>(() => parseViewFromHash(window.location.hash));
  useUrlSync(view, setView);
  // Owned here (not inside Sidebar) because the spacer below needs the SAME expansion state Sidebar
  // renders with, to size its initial width before Sidebar's own effect reports in.
  const { expanded, toggleExpanded } = useSidebarExpanded();
  // Mirrors Sidebar's actual REFLOW state (expanded on a wide viewport only — a compact viewport
  // overlays instead) via `onExpandedChange`, so the spacer below always reserves the full width and
  // content is pushed, never partially covered. (A `position: fixed` rail that's wider than this
  // spacer used to clip a sliver of content at rest — the iteration-2 sidebar-overlap regression.)
  const [sidebarWidth, setSidebarWidth] = useState(() => (expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH));
  const onSidebarExpandedChange = useCallback((expanded: boolean) => {
    setSidebarWidth(expanded ? SIDEBAR_EXPANDED_WIDTH : SIDEBAR_RAIL_WIDTH);
  }, []);

  // The ⌘K command palette is a root-level overlay, not a routed view — it must stay reachable
  // (and its state untouched) no matter which page `view` currently points at.
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  useCommandPaletteHotkey(openPalette);

  return (
    <ToastProvider>
    <NavigateProvider navigate={setView}>
    <div style={{ height: "100%", display: "flex" }}>
      <Sidebar
        view={view}
        onNavigate={setView}
        expanded={expanded}
        onToggleExpanded={toggleExpanded}
        onExpandedChange={onSidebarExpandedChange}
        onOpenPalette={openPalette}
      />
      <CommandPalette open={paletteOpen} view={view} onNavigate={setView} onClose={closePalette} />
      {/* Reserves the rail's current width in normal flow — always in lockstep with the `<nav>`'s
          own rendered width (see onSidebarExpandedChange above), so content is pushed by the FULL
          width whenever the sidebar expands, never left partially underneath it. */}
      <div style={{
        width: sidebarWidth, flexShrink: 0,
        transition: "width .16s cubic-bezier(0.22, 1, 0.36, 1)",
      }} />
      {/* A horizontal gutter so page content clears the rail's right border with breathing room
          (pages add their own inner padding on top) instead of sitting flush against the sidebar —
          fixes the "sidebar and content too tight" report. Horizontal only, so height:100% pages
          (CollectionShell) keep their full vertical box. */}
      <div style={{ flex: 1, minWidth: 0, minHeight: 0, padding: `0 ${theme.space.l}px` }}>
      {/* Keyed by view.name so navigating away (shell nav, or the fallback's own action) always
          remounts a fresh boundary — a crashed view never keeps blocking an unrelated route. */}
      <ErrorBoundary key={view.name} onReset={() => setView({ name: "overview" })}>
        {renderRoute(view, setView)}
      </ErrorBoundary>
      </div>
    </div>
    </NavigateProvider>
    </ToastProvider>
  );
}
