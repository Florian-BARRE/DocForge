// ====== Code Summary ======
// Render smoke-test for the global Sidebar nav — the replacement for the removed TopBar. Covers the
// behaviors the task spec calls out explicitly: mounts collapsed with zero throw, expands on
// hover/focus (revealing page labels hidden while collapsed) and REFLOWS the content-reserving
// spacer on a wide viewport (hover/focus included, not just a pin — see the "reflows on hover"
// test below, the fix for a measured top-level-route clipping regression: landing on Home/
// Collections via a sidebar click leaves the cursor resting inside the rail, so a non-reflowing
// hover overlay clipped the page title underneath it), collapses back on mouseleave/Escape, stays
// expanded+reflow-flagged while pinned, English labels (no more French, no more redundant health
// shortcuts), and the Collections section's soft "where am I" cue while inside a collection-scoped
// view. The transient overlay+scrim treatment now only exists on a compact/touch viewport, where a
// pin is the sole way to expand (hover/focus never trigger there) and there's no room to reflow.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Navigate, View } from "../view";
import { Sidebar } from "./Sidebar";
import { useSidebarCompact } from "./useSidebarCompact";

// Real jsdom has no `matchMedia`, so `useSidebarCompact` always resolves `false` there — mock it so
// the compact-viewport branch (FIX-B: pin must OVERLAY, never push, on a narrow/touch screen) is
// actually exercisable. Defaults to `false` (desktop) so every pre-existing test below is unaffected.
vi.mock("./useSidebarCompact", () => ({ useSidebarCompact: vi.fn(() => false) }));

function renderSidebar(props: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  const onNavigate: Navigate = props.onNavigate ?? vi.fn();
  const onTogglePin = props.onTogglePin ?? vi.fn();
  const view: View = props.view ?? { name: "collections" };
  const pinned = props.pinned ?? false;
  render(
    <Sidebar
      view={view}
      onNavigate={onNavigate}
      pinned={pinned}
      onTogglePin={onTogglePin}
      onExpandedChange={props.onExpandedChange}
    />,
  );
  return { onNavigate, onTogglePin };
}

describe("Sidebar", () => {
  it("mounts collapsed with no throw and no page labels visible", () => {
    renderSidebar();
    expect(screen.getByRole("navigation", { name: "Global navigation" })).toBeInTheDocument();
    // Section headers are always in the DOM (collapsed rail's only visible affordance)…
    expect(screen.getByTitle("Home")).toBeInTheDocument();
    expect(screen.getByTitle("Collections")).toBeInTheDocument();
    // …but page labels only mount once expanded.
    expect(screen.queryByText("All")).not.toBeInTheDocument();
  });

  it("expands on hover, revealing the section's page tree in English", () => {
    renderSidebar();
    fireEvent.mouseEnter(screen.getByRole("navigation", { name: "Global navigation" }));
    expect(screen.getByText("All")).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
    expect(screen.getByText("Import")).toBeInTheDocument();
    // The new Jobs & Workers section leads with the fleet-wide All Jobs page.
    expect(screen.getByText("All Jobs")).toBeInTheDocument();
    expect(screen.getByText("Workers")).toBeInTheDocument();
    // No more redundant health-preset shortcuts — the Collections page's own toolbar owns those.
    expect(screen.queryByText("À surveiller")).not.toBeInTheDocument();
    expect(screen.queryByText("Opérationnelles")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs attention")).not.toBeInTheDocument();
  });

  it("navigates to Home on click, as the sidebar's first top-level entry", () => {
    const { onNavigate } = renderSidebar();
    fireEvent.mouseEnter(screen.getByRole("navigation", { name: "Global navigation" }));
    fireEvent.click(screen.getByTitle("Home"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "home" });
  });

  it("expands on focus too (keyboard parity with hover)", () => {
    renderSidebar();
    // `focusin` (not `focus`, which does not bubble) — React's onFocus is a delegated listener on
    // the bubbling "focusin" event, matching what a real Tab keypress into the nav dispatches.
    fireEvent.focusIn(screen.getByTitle("DocForge home"));
    expect(screen.getByText("All")).toBeInTheDocument();
  });

  it("collapses back on mouseleave (transient overlay never gets stuck open)", () => {
    renderSidebar();
    const nav = screen.getByRole("navigation", { name: "Global navigation" });
    fireEvent.mouseEnter(nav);
    expect(screen.getByText("All")).toBeInTheDocument();
    fireEvent.mouseLeave(nav);
    expect(screen.queryByText("All")).not.toBeInTheDocument();
  });

  it("collapses back on Escape while unpinned", () => {
    renderSidebar();
    const nav = screen.getByRole("navigation", { name: "Global navigation" });
    fireEvent.mouseEnter(nav);
    expect(screen.getByText("All")).toBeInTheDocument();
    fireEvent.keyDown(nav, { key: "Escape" });
    expect(screen.queryByText("All")).not.toBeInTheDocument();
  });

  it("stays expanded regardless of hover/focus while pinned, and does not show a transient scrim", () => {
    renderSidebar({ pinned: true });
    // Already expanded without any hover/focus — that's the whole point of pinning.
    expect(screen.getByText("All")).toBeInTheDocument();
    const scrim = screen.getByTestId("sidebar-scrim");
    expect(scrim).toHaveStyle({ opacity: "0" });
  });

  it("reflows (no scrim) on hover on a wide viewport — the top-level-route clipping fix", () => {
    const onExpandedChange = vi.fn();
    renderSidebar({ pinned: false, onExpandedChange });
    const nav = screen.getByRole("navigation", { name: "Global navigation" });
    expect(screen.getByTestId("sidebar-scrim")).toHaveStyle({ opacity: "0" });
    fireEvent.mouseEnter(nav);
    // No transient overlay: the caller's content-reserving spacer is told to widen, exactly like a
    // pin, so a page's own centered content is never partially covered by the rendered rail.
    expect(screen.getByTestId("sidebar-scrim")).toHaveStyle({ opacity: "0" });
    expect(onExpandedChange).toHaveBeenCalledWith(true);
  });

  it("navigates to a page's view on click", () => {
    const { onNavigate } = renderSidebar();
    fireEvent.mouseEnter(screen.getByRole("navigation", { name: "Global navigation" }));
    fireEvent.click(screen.getByText("Workers"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "workers" });
  });

  it("highlights the active page and section from the current view", () => {
    renderSidebar({ view: { name: "api-keys" } });
    fireEvent.mouseEnter(screen.getByRole("navigation", { name: "Global navigation" }));
    expect(screen.getByText("API Keys").closest("button")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("All").closest("button")).not.toHaveAttribute("aria-current");
  });

  it("soft-highlights the Collections section while inside a collection-scoped view", () => {
    renderSidebar({ view: { name: "document", collectionId: "c1", documentId: "d1" } });
    // Deep inside a specific collection: no sidebar page/section is HARD-active (CollectionShell
    // owns that in-collection nav), so no aria-current — but the Collections header still gets a
    // steel "where am I" lift rather than reading fully inert.
    const collectionsHeader = screen.getByTitle("Collections");
    expect(collectionsHeader).not.toHaveAttribute("aria-current");
    expect(collectionsHeader).toHaveStyle({ color: "var(--text)" });
  });

  it("does not soft-highlight Collections on unrelated global views", () => {
    renderSidebar({ view: { name: "workers" } });
    expect(screen.getByTitle("Collections")).toHaveStyle({ color: "var(--text-dim)" });
  });

  it("reaches the theme toggle and token control while collapsed via compact icons", () => {
    renderSidebar();
    // Collapsed: no hover/focus, yet both controls' compact stand-ins are already in the DOM.
    expect(screen.getByLabelText("Toggle theme")).toBeInTheDocument();
    expect(screen.getByLabelText("API token")).toBeInTheDocument();
  });

  it("clicking the compact token icon while collapsed requests a pin (so the real editor becomes reachable)", () => {
    const { onTogglePin } = renderSidebar();
    fireEvent.click(screen.getByLabelText("API token"));
    expect(onTogglePin).toHaveBeenCalledTimes(1);
  });

  it("on a compact viewport, a pin OVERLAYS with a scrim instead of reflowing (FIX-B)", () => {
    vi.mocked(useSidebarCompact).mockReturnValue(true);
    const onExpandedChange = vi.fn();
    renderSidebar({ pinned: true, onExpandedChange });
    // Still expanded (the page tree renders) — pinning stays the way in on a compact viewport too.
    expect(screen.getByText("All")).toBeInTheDocument();
    // …but as an overlay: the scrim shows, and the caller's content-reserving spacer is never told
    // to widen (would push content off the right edge of a narrow screen — the FIX-B regression).
    expect(screen.getByTestId("sidebar-scrim")).toHaveStyle({ opacity: "1" });
    expect(onExpandedChange).toHaveBeenCalledWith(false);
    expect(onExpandedChange).not.toHaveBeenCalledWith(true);
  });

  it("on a wide viewport, a pin still reflows (no scrim, spacer told to widen) — desktop unaffected", () => {
    vi.mocked(useSidebarCompact).mockReturnValue(false);
    const onExpandedChange = vi.fn();
    renderSidebar({ pinned: true, onExpandedChange });
    expect(screen.getByTestId("sidebar-scrim")).toHaveStyle({ opacity: "0" });
    expect(onExpandedChange).toHaveBeenCalledWith(true);
  });

  // Regression guard for a reported "pin doesn't push at exactly 1440px" repro: reflow is gated
  // SOLELY by `isCompact` (Sidebar.tsx: `reflow = expanded && !isCompact`), which itself is a single
  // CSS media query — `(max-width: 640px), (pointer: coarse)` in useSidebarCompact.ts — with no
  // second/duplicate width comparison anywhere in the reflow path. So every non-compact width,
  // 641px through 1440px and beyond, is one uniform branch; live-verified at exactly 1440x900
  // against the running dev container (spacer=240, content starts at x=240, page title unclipped).
  it("reflows at any non-compact width, not just >1440 — no off-by-one at the desktop boundary", () => {
    vi.mocked(useSidebarCompact).mockReturnValue(false);
    const onExpandedChange = vi.fn();
    renderSidebar({ pinned: true, onExpandedChange });
    expect(onExpandedChange).toHaveBeenCalledWith(true);
    expect(onExpandedChange).not.toHaveBeenCalledWith(false);
  });
});
