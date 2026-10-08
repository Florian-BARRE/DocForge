// ====== Code Summary ======
// The reindex banner offers "Rebuild index" behind a confirm dialog; confirming POSTs the rebuild and
// notifies the parent so it can refetch the collection.

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../../shell/toast";
import { ReindexBanner, reindexNeeded } from "./ReindexBanner";
import { REBUILD_POLL_INTERVAL_MS } from "./useRebuildPolling";

vi.mock("../../api/collections", () => ({ rebuildCollectionIndex: vi.fn() }));
const { rebuildCollectionIndex } = await import("../../api/collections");

describe("ReindexBanner", () => {
  it("reports a reindex need from either needs_reindex or missing vectors", () => {
    expect(reindexNeeded({ needs_reindex: false, missing_vectors: ["meta_x_dense"] })).toBe(true);
    expect(reindexNeeded({ needs_reindex: false, missing_vectors: [] })).toBe(false);
  });

  it("confirms, rebuilds and notifies the parent", async () => {
    vi.mocked(rebuildCollectionIndex).mockResolvedValue({ collection_id: "c1", job_id: "j1" });
    const onStarted = vi.fn();
    render(
      <ToastProvider>
        <ReindexBanner collection={{ id: "c1", needs_reindex: true, missing_vectors: ["meta_x_dense"] }} onStarted={onStarted} />
      </ToastProvider>,
    );
    expect(screen.getByText("meta_x_dense")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rebuild index" }));
    expect(rebuildCollectionIndex).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Rebuild index" }));
    await waitFor(() => expect(rebuildCollectionIndex).toHaveBeenCalledWith("c1"));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
  });

  it("keeps refetching while the rebuild runs so the parent can drop the banner", async () => {
    vi.mocked(rebuildCollectionIndex).mockResolvedValue({ collection_id: "c1", job_id: "j1" });
    const onStarted = vi.fn();
    render(
      <ToastProvider>
        <ReindexBanner collection={{ id: "c1", needs_reindex: true, missing_vectors: [] }} onStarted={onStarted} />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Rebuild index" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Rebuild index" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: "Rebuilding…" })).toBeDisabled();
    await waitFor(() => expect(onStarted.mock.calls.length).toBeGreaterThan(1), { timeout: REBUILD_POLL_INTERVAL_MS + 2000 });
  }, 10000);
});
