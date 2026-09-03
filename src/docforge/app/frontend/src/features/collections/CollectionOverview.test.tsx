// ====== Code Summary ======
// Render smoke-test for the loading→loaded transition of CollectionOverview — the exact shape of
// bug that bricked the whole app: a hook called AFTER a conditional early-return (Rules of Hooks
// violation) only throws once the component re-renders past `loading` into its loaded branches.
// `tsc --noEmit` and `vite build` both stay green on that bug (it is a runtime violation, not a
// type error), so this test is the gate's only line of defense against a repeat. Two loaded shapes
// are covered — an empty collection (0 docs, the "upload hero" branch) and a populated one (N
// docs, the "health board + stats" branch) — since they render disjoint hook-dependent JSX trees.

import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { Collection, CollectionHealth, CollectionStorage } from "../../api/collections";
import type { DocumentListItem } from "../../api/explorer";
import { ToastProvider } from "../../shell/toast";
import { CollectionOverview } from "./CollectionOverview";

// `useHideHeaderUpload` (CollectionShell's HideHeaderUploadContext) is a documented no-op outside
// its provider by design (see that hook's docstring) — safe to exercise unwrapped here. `useToast`
// has no such default (throws by design, see shell/toast.tsx), so the tree needs a real
// <ToastProvider> — UploadPanel (rendered on the 0-doc branch) calls it unconditionally.
function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  getCollection: vi.fn(),
  getCollectionHealth: vi.fn(),
  fetchCollectionStorage: vi.fn(),
}));

vi.mock("../../api/explorer", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/explorer")>()),
  listDocuments: vi.fn(),
}));

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  listJobs: vi.fn(),
}));

const { getCollection, getCollectionHealth, fetchCollectionStorage } = await import("../../api/collections");
const { listDocuments } = await import("../../api/explorer");
const { listJobs } = await import("../../api/jobs");

const baseCollection: Collection = {
  id: "col-1",
  name: "Test Collection",
  supported_formats: ["pdf"],
  max_file_size_bytes: 10_000_000,
  job_timeout_seconds: null,
  needs_reindex: false,
  created_at: "2026-01-01T00:00:00Z",
  pipeline: {},
  search: {},
  fields: [],
  estimate_overrides: null,
};

const baseHealth: CollectionHealth = {
  collection_id: "col-1",
  verdict: "empty",
  reason: "No documents ingested yet.",
  checked_at: "2026-01-01T00:00:00Z",
  ingest: { buildable: true, build_error: null, providers: [] },
  search: { buildable: true, search_operational: true, build_error: null, providers: [], index: { vector_count: 0, last_ingest_at: null } },
};

const baseStorage: CollectionStorage = {
  collection_id: "col-1",
  s3: { original_bytes: 0, rendered_bytes: 0, total_bytes: 0, physical_unique_bytes: 0, estimated: false },
  postgres: { documents_bytes: 0, ir_blocks_bytes: 0, enrichment_bytes: 0, chunks_bytes: 0, metadata_bytes: 0, observability_bytes: 0, total_bytes: 0, estimated: false },
  qdrant: { points: 0, dense_bytes: 0, sparse_bytes: 0, payload_bytes: 0, total_bytes: 0, estimated: false },
  grand_total_bytes: 0,
  documents: [],
};

function documentFixture(id: string): DocumentListItem {
  return {
    id,
    filename: `${id}.pdf`,
    format: "pdf",
    status: "done",
    page_count: 3,
    file_size: 1234,
    created_at: "2026-01-01T00:00:00Z",
    title: `Document ${id}`,
    language: "en",
    enabled: true,
  };
}

describe("CollectionOverview — loading to loaded transition", () => {
  it("mounts through loading -> loaded with 0 documents without throwing", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    vi.mocked(listDocuments).mockResolvedValue([]);
    vi.mocked(getCollectionHealth).mockResolvedValue(baseHealth);
    vi.mocked(listJobs).mockResolvedValue([]);

    expect(() => renderWithProviders(<CollectionOverview collectionId="col-1" onNavigate={vi.fn()} />)).not.toThrow();

    // While the initial fetches are in flight the component is still in its "loading" branch.
    expect(screen.getByText("loading overview…")).toBeInTheDocument();

    // Past the transition: the empty-collection upload hero renders, not the loading state.
    await waitFor(() => expect(screen.getByText("Upload your first document")).toBeInTheDocument());
    expect(screen.queryByText("loading overview…")).not.toBeInTheDocument();
  });

  it("mounts through loading -> loaded with N documents without throwing", async () => {
    vi.mocked(getCollection).mockResolvedValue(baseCollection);
    vi.mocked(listDocuments).mockResolvedValue([documentFixture("doc-1"), documentFixture("doc-2")]);
    vi.mocked(getCollectionHealth).mockResolvedValue(baseHealth);
    vi.mocked(fetchCollectionStorage).mockResolvedValue(baseStorage);
    vi.mocked(listJobs).mockResolvedValue([]);

    expect(() => renderWithProviders(<CollectionOverview collectionId="col-1" onNavigate={vi.fn()} />)).not.toThrow();

    expect(screen.getByText("loading overview…")).toBeInTheDocument();

    // Past the transition: the health board + stat strip render, not the loading state or the
    // empty-collection upload hero.
    await waitFor(() => expect(screen.getByText("Collection health")).toBeInTheDocument());
    expect(screen.queryByText("loading overview…")).not.toBeInTheDocument();
    expect(screen.queryByText("Upload your first document")).not.toBeInTheDocument();
  });
});
