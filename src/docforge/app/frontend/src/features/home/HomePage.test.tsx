// ====== Code Summary ======
// Render smoke-test for HomePage, the fleet cockpit — mounts through loading -> loaded for its
// independently-fetched LINK tiles (collections fleet, workers, queue, recent failures) without
// throwing, and covers click-throughs from the "Need attention" tile (Collections preset) and the
// recent-failures tile (Activity ▸ Failures).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection, CollectionHealth } from "../../api/collections";
import type { FailureBreakdown, QueueDepth, WorkersLive } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { HomePage } from "./HomePage";

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  listCollections: vi.fn(),
  getCollectionHealth: vi.fn(),
}));

vi.mock("../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/corpus")>()),
  queryDocuments: vi.fn(),
}));

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  getQueueDepth: vi.fn(),
  getWorkersLive: vi.fn(),
  getFailureBreakdown: vi.fn(),
}));

const { listCollections, getCollectionHealth } = await import("../../api/collections");
const { queryDocuments } = await import("../../api/corpus");
const { getQueueDepth, getWorkersLive, getFailureBreakdown } = await import("../../api/jobs");

const collection: Collection = {
  id: "col-1", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, fields: [], estimate_overrides: null, trace_verbosity: "shape", tags: [],
};

const downHealth: CollectionHealth = {
  collection_id: "col-1", verdict: "down", reason: "Search graph is unreachable.",
  checked_at: "2026-01-01T00:00:00Z",
  ingest: { buildable: true, build_error: null, providers: [] },
  search: { buildable: false, search_operational: false, build_error: "boom", providers: [], index: { vector_count: 0, last_ingest_at: null } },
};

const emptyQueue: QueueDepth = { pending: 0, running: 0 };
const emptyWorkers: WorkersLive = { workers: [] };
const emptyBreakdown: FailureBreakdown = {
  collection_id: null, window_hours: 24, since: "2026-01-01T00:00:00Z", total_failed: 0,
  by_error_type: [], by_stage: [], by_collection: [],
};

describe("HomePage", () => {
  it("mounts through loading -> loaded across its independent tiles without throwing", async () => {
    vi.mocked(listCollections).mockResolvedValue([collection]);
    vi.mocked(getCollectionHealth).mockResolvedValue(downHealth);
    vi.mocked(queryDocuments).mockResolvedValue({ total: 3, limit: 1, offset: 0, rows: [] });
    vi.mocked(getQueueDepth).mockResolvedValue(emptyQueue);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);
    vi.mocked(getFailureBreakdown).mockResolvedValue(emptyBreakdown);

    const onNavigate: Navigate = vi.fn();
    expect(() => render(<HomePage onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("1", { exact: true })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Recent failures")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Need attention"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "collections", health: "attention" });

    fireEvent.click(screen.getByText("Recent failures"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "activity", tab: "failures" });
  });
});
