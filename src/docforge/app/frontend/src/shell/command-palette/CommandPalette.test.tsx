// ====== Code Summary ======
// Render smoke-test for the ⌘K command palette: closed renders nothing, open focuses the input and
// lists Go-to/Actions/Collections, typing filters across all groups, and Enter navigates + closes.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection } from "../../api/collections";
import type { Navigate, View } from "../view";
import { CommandPalette } from "./CommandPalette";

const collections: Collection[] = [
  {
    id: "c1", name: "Regulatory filings", supported_formats: ["pdf"], tags: ["legal"],
    max_file_size_bytes: 1, job_timeout_seconds: null, needs_reindex: false, created_at: null,
    pipeline: {}, search: {}, fields: [], estimate_overrides: null, trace_verbosity: "shape",
  },
  {
    id: "c2", name: "Support tickets", supported_formats: ["pdf"], tags: [],
    max_file_size_bytes: 1, job_timeout_seconds: null, needs_reindex: false, created_at: null,
    pipeline: {}, search: {}, fields: [], estimate_overrides: null, trace_verbosity: "shape",
  },
];

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  listCollections: vi.fn(() => Promise.resolve(collections)),
}));

function renderPalette(view: View = { name: "overview" }) {
  const onNavigate: Navigate = vi.fn();
  const onClose = vi.fn();
  render(<CommandPalette open view={view} onNavigate={onNavigate} onClose={onClose} />);
  return { onNavigate, onClose };
}

describe("CommandPalette", () => {
  it("renders nothing when closed", () => {
    render(<CommandPalette open={false} view={{ name: "overview" }} onNavigate={vi.fn()} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens with focus in the search input and the deployment Go-to destinations listed", async () => {
    renderPalette();
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    const input = screen.getByRole("combobox", { name: "Command palette search" });
    expect(input).toHaveFocus();
    for (const label of ["Overview", "Activity", "Fleet", "Settings"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // "Collections" is both a group heading and a Go-to destination label — assert the option row.
    expect(screen.getByRole("option", { name: "Collections" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Regulatory filings")).toBeInTheDocument());
    expect(screen.getByText("Support tickets")).toBeInTheDocument();
  });

  it("filters results as the query changes, across collections and go-to destinations", async () => {
    renderPalette();
    await waitFor(() => expect(screen.getByText("Regulatory filings")).toBeInTheDocument());

    const input = screen.getByRole("combobox", { name: "Command palette search" });
    fireEvent.change(input, { target: { value: "regu" } });

    expect(screen.getByText("Regulatory filings")).toBeInTheDocument();
    expect(screen.queryByText("Support tickets")).not.toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
  });

  it("navigates to a collection on Enter and closes the palette", async () => {
    const { onNavigate, onClose } = renderPalette();
    await waitFor(() => expect(screen.getByText("Regulatory filings")).toBeInTheDocument());

    const input = screen.getByRole("combobox", { name: "Command palette search" });
    fireEvent.change(input, { target: { value: "regulatory" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onNavigate).toHaveBeenCalledWith({ name: "collection", collectionId: "c1" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("moves the selection with arrow keys before activating with Enter", () => {
    const { onNavigate } = renderPalette();
    const input = screen.getByRole("combobox", { name: "Command palette search" });
    fireEvent.change(input, { target: { value: "fleet" } });
    // A single match ("Fleet") — ArrowDown should wrap back onto the same item, not throw.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onNavigate).toHaveBeenCalledWith({ name: "fleet" });
  });

  it("closes the palette when clicking the scrim", () => {
    const { onClose } = renderPalette();
    fireEvent.click(screen.getByRole("dialog", { name: "Command palette" }).parentElement as HTMLElement);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("surfaces the contextual actions and Go-to tabs while inside a collection", () => {
    renderPalette({ name: "collection-documents", collectionId: "c1" });
    expect(screen.getByText("Upload to this collection")).toBeInTheDocument();
    expect(screen.getAllByText("this collection").length).toBeGreaterThan(0);
  });
});
