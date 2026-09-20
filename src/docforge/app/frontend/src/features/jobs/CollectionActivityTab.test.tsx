// ====== Code Summary ======
// Render smoke-test for CollectionActivityTab — the collection-scoped mirror of ActivityPage's Jobs
// tab (see ActivityPage.test.tsx). Covers the loading -> loaded transition and asserts the scoping
// contract: every fetch is pinned to `collectionId` and the cross-collection facet never renders.

import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { JobPage, JobStatus, QueueDepth, WorkersLive } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { ToastProvider } from "../../shell/toast";
import { CollectionActivityTab } from "./CollectionActivityTab";

// JobRow renders JobCancelControl, which calls useToast() unconditionally — needs a real provider
// (the ToastProvider harness gotcha).
function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/jobs")>()),
  listJobsPage: vi.fn(),
  getWorkersLive: vi.fn(),
  getQueueDepth: vi.fn(),
}));

const { listJobsPage, getWorkersLive, getQueueDepth } = await import("../../api/jobs");

function jobFixture(overrides: Partial<JobStatus>): JobStatus {
  return {
    job_id: "job-1",
    document_id: "doc-1",
    document_filename: "report.pdf",
    document_title: null,
    collection_id: "col-1",
    collection_name: "Contracts",
    status: "pending",
    cancel_requested: false,
    progress: 0,
    current_stage: null,
    error: null,
    attempt: 1,
    started_at: null,
    finished_at: null,
    updated_at: "2026-01-01T00:00:00Z",
    stalled: false,
    duration_seconds: null,
    total_prompt_tokens: 0,
    total_completion_tokens: 0,
    cost_usd: 0,
    items_done: null,
    items_total: null,
    failed_node_id: null,
    failed_node_kind: null,
    failed_item_index: null,
    error_type: null,
    ...overrides,
  };
}

const emptyWorkers: WorkersLive = { workers: [] };
const emptyDepth: QueueDepth = { pending: 0, running: 0 };

describe("CollectionActivityTab", () => {
  it("mounts through loading -> loaded, scoping the fetch to this collection with no cross-collection facet", async () => {
    const page: JobPage = { total: 1, limit: 25, offset: 0, jobs: [jobFixture({})] };
    vi.mocked(listJobsPage).mockResolvedValue(page);
    vi.mocked(getWorkersLive).mockResolvedValue(emptyWorkers);
    vi.mocked(getQueueDepth).mockResolvedValue(emptyDepth);

    const onNavigate: Navigate = vi.fn();
    expect(() =>
      renderWithProviders(<CollectionActivityTab collectionId="col-1" onNavigate={onNavigate} />),
    ).not.toThrow();

    expect(screen.getByText("loading jobs…")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("report.pdf")).toBeInTheDocument());
    expect(screen.queryByText("loading jobs…")).not.toBeInTheDocument();

    expect(listJobsPage).toHaveBeenCalledWith(expect.objectContaining({ collectionId: "col-1" }));
    expect(getQueueDepth).toHaveBeenCalledWith("col-1");
    expect(screen.queryByLabelText("Filter jobs by collection")).not.toBeInTheDocument();
  });
});
