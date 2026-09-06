// ====== Code Summary ======
// Render smoke-test for HomePage, the new default landing — mounts through loading -> loaded for
// its independently-fetched tiles (collections fleet, workers, recent failures) without throwing,
// and covers a click-through from the "Need attention" tile to the Collections preset view.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Collection, CollectionHealth } from "../../api/collections";
import type { QueueDepth, WorkersLive } from "../../api/jobs";
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
  listJobsPage: vi.fn(),
}));

const { listCollections, getCollectionHealth } = await import("../../api/collections");
const { queryDocuments } = await import("../../api/corpus");
const { getQueueDepth, getWorkersLive, listJobsPage } = await import("../../api/jobs");

const collection: Collection = {
  id: "col-1", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, fields: [], estimate_overrides: null,
};

const downHealth: CollectionHealth = {
  collection_id: "col-1", verdict: "down", reason: "Search graph is unreachable.",
  checked_at: "2026-01-01T00:00:00Z",
  ingest: { buildable: true, build_error: null, providers: [] },
  search: { buildable: false, search_operational: false, build_error: "boom", providers: [], index: { vector_count: 0, last_ingest_at: null } },
};

const emptyQueue: QueueDepth = { pending: 0, running: 0 };
const emptyWorkers: WorkersLive = { workers: [] };

describe("HomePage", () => {
  it("mounts through loading -> loaded across its independent tiles without throwing", async () => {
    vi.mocked(listCollections).mockResolvedValue([collection]);
    vi.mocked(getCollectionHealth).mockResolvedValue(downHealth);
    vi.mocked(queryDocuments).mockResolvedValue({ total: 3, limit: 1, offset: 0, rows: [] });
    vi.mocked(getQueueDepth).mockResolvedValue(emptyQueue);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);
    vi.mocked(listJobsPage).mockResolvedValue({ total: 0, limit: 5, offset: 0, jobs: [] });

    const onNavigate: Navigate = vi.fn();
    expect(() => render(<HomePage onNavigate={onNavigate} />)).not.toThrow();

    await waitFor(() => expect(screen.getByText("1", { exact: true })).toBeInTheDocument());
    expect(screen.getByText("No recent failures")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Need attention"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "collections", health: "attention" });
  });
});
