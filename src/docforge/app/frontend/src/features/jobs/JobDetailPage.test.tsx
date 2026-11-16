// ====== Code Summary ======
// Render smoke-test for JobDetailPage's kind handling: a metadata_sync job shows the "metadata sync"
// badge and NONE of the ingest-only re-run/force controls; an ingest job keeps them.

import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import type { JobStatus } from "../../api/jobs";
import { ToastProvider } from "../../shell/toast";
import { JobDetailPage } from "./JobDetailPage";

const mockState = vi.hoisted(() => ({ job: null as unknown }));

vi.mock("./state/useJobDetail", () => ({
  useJobDetail: () => ({
    job: mockState.job, events: [], error: null, live: false, patchJob: vi.fn(),
    running: false, elapsedInStageSeconds: null, avgStageSeconds: undefined,
    runningLong: false, etaSeconds: null, totalTokens: 0,
  }),
}));

function jobFixture(kind: string): JobStatus {
  return {
    job_id: "job-1", kind, document_id: "doc-1", document_filename: "report.pdf", document_title: null,
    collection_id: "col-1", collection_name: "Contracts", status: "done", cancel_requested: false,
    progress: 100, current_stage: null, error: null, attempt: 1, started_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:00:05Z", updated_at: "2026-01-01T00:00:05Z", stalled: false, duration_seconds: 5,
    total_prompt_tokens: 0, total_completion_tokens: 0, cost_usd: 0, items_done: null, items_total: null,
    failed_node_id: null, failed_node_kind: null, failed_item_index: null, error_type: null,
  } as JobStatus;
}

function mount() {
  return render(<ToastProvider><JobDetailPage jobId="job-1" collectionId="col-1" onNavigate={vi.fn()} /></ToastProvider>);
}

describe("JobDetailPage kind handling", () => {
  afterEach(() => cleanup());

  it("shows the kind badge and hides re-run/force for a metadata_sync job", () => {
    mockState.job = jobFixture("metadata_sync");
    mount();
    expect(screen.getByText("metadata sync")).toBeTruthy();
    expect(screen.queryByText("Re-run (cached)")).toBeNull();
    expect(screen.queryByText("Force (no cache)")).toBeNull();
  });

  it("keeps re-run/force for an ingest job", () => {
    mockState.job = jobFixture("ingest");
    mount();
    expect(screen.getByText("ingestion")).toBeTruthy();
    expect(screen.getByText("Re-run (cached)")).toBeTruthy();
  });
});
