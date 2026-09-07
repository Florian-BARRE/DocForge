// ====== Code Summary ======
// Focused test for the worker-card layout toggle: switching segments derives the right
// `gridTemplateColumns`, and the choice round-trips through localStorage via useWorkersLayout
// (default "auto" when storage is empty/unreadable, matching useSidebarPin's try/catch pattern).

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { gridTemplateColumnsFor, useWorkersLayout } from "./state/useWorkersLayout";
import { WorkerLayoutToggle } from "./WorkerLayoutToggle";

const STORAGE_KEY = "docforge_workers_layout";

function ToggleHarness() {
  const { layout, setLayout } = useWorkersLayout();
  return (
    <div>
      <span data-testid="grid-columns">{gridTemplateColumnsFor(layout)}</span>
      <WorkerLayoutToggle layout={layout} onChange={setLayout} />
    </div>
  );
}

describe("WorkerLayoutToggle", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("defaults to Auto when nothing is persisted", () => {
    render(<ToggleHarness />);
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(auto-fill, minmax(320px, 1fr))");
  });

  it("switches to List (single column) and persists the choice", () => {
    render(<ToggleHarness />);
    fireEvent.click(screen.getByRole("radio", { name: "List" }));

    expect(screen.getByRole("radio", { name: "List" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("1fr");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("list");
  });

  it("switches to a fixed column count and derives repeat(N, minmax(0, 1fr))", () => {
    render(<ToggleHarness />);
    fireEvent.click(screen.getByRole("radio", { name: "3 columns" }));

    expect(screen.getByRole("radio", { name: "3 columns" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(3, minmax(0, 1fr))");
    expect(localStorage.getItem(STORAGE_KEY)).toBe("3");
  });

  it("round-trips a persisted choice across mounts", () => {
    localStorage.setItem(STORAGE_KEY, "2");
    render(<ToggleHarness />);
    expect(screen.getByRole("radio", { name: "2 columns" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByTestId("grid-columns")).toHaveTextContent("repeat(2, minmax(0, 1fr))");
  });

  it("falls back to auto for an unreadable/corrupt stored value", () => {
    localStorage.setItem(STORAGE_KEY, "not-a-layout");
    render(<ToggleHarness />);
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "true");
  });
});
