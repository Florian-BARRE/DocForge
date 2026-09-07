// ====== Code Summary ======
// Covers the shared view switcher end to end: grid/list clicks, the long-press path into the
// column-count popover, picking a column count, and the underlying useViewMode persistence
// (round-trip per storage key + fallback to grid+auto for a corrupt/unreadable stored value) —
// the same contract the deleted WorkerLayoutToggle.test.tsx covered for the old segmented control.

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { gridTemplateColumnsFor, useViewMode } from "./useViewMode";
import { ViewModeToggle } from "./ViewModeToggle";

const STORAGE_KEY = "docforge_view_test";

function ToggleHarness() {
  const { mode, setMode } = useViewMode(STORAGE_KEY);
  return (
    <div>
      <span data-testid="grid-columns">{gridTemplateColumnsFor(mode, 300)}</span>
      <ViewModeToggle mode={mode} onChange={setMode} label="Test" />
    </div>
  );
}

describe("ViewModeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to grid+auto when nothing is persisted", () => {
    render(<ToggleHarness />);
    expect(screen.getByRole("button", { name: /grid view/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(auto-fill, minmax(300px, 1fr))");
  });

  it("switches to list on click and persists it", () => {
    render(<ToggleHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Test list view" }));

    expect(screen.getByRole("button", { name: "Test list view" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("1fr");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({ kind: "list" });
  });

  it("a plain click back to grid restores the last column count", () => {
    render(<ToggleHarness />);
    const gridButton = screen.getByRole("button", { name: /grid view/ });
    // Open the popover via keyboard (no hold needed) and pick "3".
    fireEvent.keyDown(gridButton, { key: "ArrowDown" });
    fireEvent.click(screen.getByRole("menuitemradio", { name: "3" }));
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(3, minmax(0, 1fr))");

    fireEvent.click(screen.getByRole("button", { name: "Test list view" }));
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("1fr");

    fireEvent.click(gridButton);
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(3, minmax(0, 1fr))");
  });

  it("long-pressing the grid button opens the column popover", () => {
    vi.useFakeTimers();
    try {
      render(<ToggleHarness />);
      const gridButton = screen.getByRole("button", { name: /grid view/ });

      fireEvent.pointerDown(gridButton, { button: 0 });
      expect(screen.queryByRole("menu", { name: "Columns per row" })).not.toBeInTheDocument();
      // The component's own setTimeout callback flips React state — advancing fake timers outside
      // `act` leaves that update unflushed, so the assertion right after would still see the old DOM.
      act(() => { vi.advanceTimersByTime(500); });
      expect(screen.getByRole("menu", { name: "Columns per row" })).toBeInTheDocument();
      fireEvent.pointerUp(gridButton);
    } finally {
      vi.useRealTimers();
    }
  });

  it("a short click (released before the long-press threshold) does NOT open the popover", () => {
    vi.useFakeTimers();
    try {
      render(<ToggleHarness />);
      const gridButton = screen.getByRole("button", { name: /grid view/ });

      fireEvent.pointerDown(gridButton, { button: 0 });
      act(() => { vi.advanceTimersByTime(100); });
      fireEvent.pointerUp(gridButton);
      fireEvent.click(gridButton);
      act(() => { vi.advanceTimersByTime(500); });
      expect(screen.queryByRole("menu", { name: "Columns per row" })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("right-click (mouse, no hold) opens the column popover — the pointer-only accessible fallback", () => {
    render(<ToggleHarness />);
    const gridButton = screen.getByRole("button", { name: /grid view/ });
    fireEvent.contextMenu(gridButton);
    expect(screen.getByRole("menu", { name: "Columns per row" })).toBeInTheDocument();
  });

  it("ArrowDown on the focused grid button opens the column popover — the keyboard-only accessible fallback", () => {
    render(<ToggleHarness />);
    const gridButton = screen.getByRole("button", { name: /grid view/ });
    gridButton.focus();
    fireEvent.keyDown(gridButton, { key: "ArrowDown" });
    expect(screen.getByRole("menu", { name: "Columns per row" })).toBeInTheDocument();
  });

  it("picking a column count sets grid+N and closes the popover", () => {
    render(<ToggleHarness />);
    const gridButton = screen.getByRole("button", { name: /grid view/ });
    fireEvent.contextMenu(gridButton);
    fireEvent.click(screen.getByRole("menuitemradio", { name: "4" }));

    expect(screen.queryByRole("menu", { name: "Columns per row" })).not.toBeInTheDocument();
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(4, minmax(0, 1fr))");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({ kind: "grid", columns: 4 });
  });

  it("round-trips a persisted grid+N choice across mounts", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ kind: "grid", columns: 2 }));
    render(<ToggleHarness />);
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(2, minmax(0, 1fr))");
  });

  it("falls back to grid+auto for a corrupt/unreadable stored value", () => {
    localStorage.setItem(STORAGE_KEY, "not-json");
    render(<ToggleHarness />);
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(auto-fill, minmax(300px, 1fr))");
  });
});
