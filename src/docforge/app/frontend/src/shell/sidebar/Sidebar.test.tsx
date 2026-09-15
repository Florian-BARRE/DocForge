// ====== Code Summary ======
// Render smoke-test for the redesigned global Sidebar — a PERSISTENT rail (expanded by default),
// collapsing to the icon rail only via the explicit footer toggle (never hover/focus-gated). Covers
// the behaviours the IA redesign (Wave 1) fixes: a flat deployment-scope nav (Overview / Collections /
// Activity / Fleet / Settings, all English), the brand wordmark home → the `overview` view, the
// forge-accent HARD-active page via aria-current, the steel SOFT "where am I" cue on Collections while
// inside a specific collection (no aria-current then), the always-visible footer account controls
// (theme toggle + API token) reachable even while collapsed, and the explicit expand/collapse toggle.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Navigate, View } from "../view";
import { Sidebar } from "./Sidebar";
import { useSidebarCompact } from "./useSidebarCompact";

// Real jsdom has no `matchMedia`, so mock the compact hook to a stable desktop `false` (the reflow
// path) — the compact/overlay branch is toggled explicitly in the one test that needs it.
vi.mock("./useSidebarCompact", () => ({ useSidebarCompact: vi.fn(() => false) }));

function renderSidebar(props: Partial<Parameters<typeof Sidebar>[0]> = {}) {
  const onNavigate: Navigate = props.onNavigate ?? vi.fn();
  const onToggleExpanded = props.onToggleExpanded ?? vi.fn();
  const view: View = props.view ?? { name: "collections" };
  const expanded = props.expanded ?? true;
  render(
    <Sidebar
      view={view}
      onNavigate={onNavigate}
      expanded={expanded}
      onToggleExpanded={onToggleExpanded}
      onExpandedChange={props.onExpandedChange}
    />,
  );
  return { onNavigate, onToggleExpanded };
}

describe("Sidebar", () => {
  it("mounts expanded with the flat English nav and no throw", () => {
    renderSidebar();
    expect(screen.getByRole("navigation", { name: "Global navigation" })).toBeInTheDocument();
    for (const label of ["Overview", "Collections", "Activity", "Fleet", "Settings"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // No leftover French / two-level section labels from the old rail.
    expect(screen.queryByText("Pipeline de recherche")).not.toBeInTheDocument();
    expect(screen.queryByText("All Jobs")).not.toBeInTheDocument();
  });

  it("collapsed hides labels but keeps titles + footer account controls reachable", () => {
    renderSidebar({ expanded: false });
    // Labels only mount when expanded…
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    // …but each item keeps its title (icon-only rail stays navigable), and the footer's compact
    // theme/token stand-ins are present WITHOUT any hover — the "chrome hidden behind hover" fix.
    expect(screen.getByTitle("Fleet")).toBeInTheDocument();
    expect(screen.getByLabelText("Toggle theme")).toBeInTheDocument();
    expect(screen.getByLabelText("API token")).toBeInTheDocument();
  });

  it("navigates to the overview view from the brand home button", () => {
    const { onNavigate } = renderSidebar();
    fireEvent.click(screen.getByTitle("DocForge home"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "overview" });
  });

  it("navigates to a nav item's view on click", () => {
    const { onNavigate } = renderSidebar();
    fireEvent.click(screen.getByText("Fleet"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "fleet" });
  });

  it("marks the current page HARD-active via aria-current, and only that one", () => {
    renderSidebar({ view: { name: "fleet" } });
    expect(screen.getByText("Fleet").closest("button")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Overview").closest("button")).not.toHaveAttribute("aria-current");
  });

  it("swaps to the collection nav inside a collection-scoped view (Supabase-style scope swap)", () => {
    renderSidebar({ view: { name: "document", collectionId: "c1", documentId: "d1" } });
    // The rail now OWNS the in-collection nav: a back item + the 7 collection pages, not the
    // deployment nav (no top-level "Activity"/"Fleet" here) and no redundant horizontal tab strip.
    expect(screen.getByTitle("All collections")).toBeInTheDocument();
    for (const label of ["Overview", "Documents", "Search", "Pipelines", "Schema", "Activity", "Settings"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText("Fleet")).not.toBeInTheDocument();
    // A document is nested under Documents, which stays HARD-active for it.
    expect(screen.getByText("Documents").closest("button")).toHaveAttribute("aria-current", "page");
  });

  it("fires onOpenPalette from the ⌘K trigger near the brand mark", () => {
    const onOpenPalette = vi.fn();
    render(
      <Sidebar
        view={{ name: "overview" }}
        onNavigate={vi.fn()}
        expanded
        onToggleExpanded={vi.fn()}
        onOpenPalette={onOpenPalette}
      />,
    );
    fireEvent.click(screen.getByTitle("Command palette (⌘K)"));
    expect(onOpenPalette).toHaveBeenCalledTimes(1);
  });

  it("fires onToggleExpanded from the explicit footer collapse toggle", () => {
    const { onToggleExpanded } = renderSidebar({ expanded: true });
    fireEvent.click(screen.getByTitle("Collapse sidebar"));
    expect(onToggleExpanded).toHaveBeenCalledTimes(1);
  });

  it("on a compact viewport, expansion floats over a scrim instead of reflowing", () => {
    vi.mocked(useSidebarCompact).mockReturnValue(true);
    const onExpandedChange = vi.fn();
    renderSidebar({ expanded: true, onExpandedChange });
    expect(screen.getByTestId("sidebar-scrim")).toHaveStyle({ opacity: "1" });
    // No reflow on compact — the caller's content spacer is never told to widen.
    expect(onExpandedChange).toHaveBeenCalledWith(false);
    vi.mocked(useSidebarCompact).mockReturnValue(false);
  });
});
