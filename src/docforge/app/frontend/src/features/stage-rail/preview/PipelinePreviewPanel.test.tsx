// ====== Code Summary ======
// Render smoke-test for the dry-run panel's loading -> done and loading -> failed transitions — the
// two states a bare `tsc` pass cannot catch (a hooks-order regression, a null-result crash).

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PreviewJobResult } from "../../../api/preview";
import type { GroupBlob } from "../../../api/types";
import { PipelinePreviewPanel } from "./PipelinePreviewPanel";

vi.mock("../../../api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/preview")>()),
  submitPreviewJob: vi.fn(),
  getPreviewJob: vi.fn(),
}));
vi.mock("../../../api/corpus", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../api/corpus")>()),
  queryDocuments: vi.fn(),
}));

const { submitPreviewJob, getPreviewJob } = await import("../../../api/preview");
const { queryDocuments } = await import("../../../api/corpus");

const blob = { node_type: "group", id: "root", nodes: [], transitions: [], bindings: {} } as unknown as GroupBlob;

const doneResult: PreviewJobResult = {
  preview_id: "p-1",
  status: "done",
  error: null,
  result: {
    ok: true,
    source_filename: "sample.pdf",
    ir: {
      title: "Sample", language: "en", page_count: 2, source_format: "pdf", file_size: 1024,
      source_hash: "abc123", block_count: 5, block_type_counts: { paragraph: 5 }, figure_count: 0,
    },
    chunk_count: 1,
    chunks: [{
      chunk_id: "c1", ordinal: 0, role: "body", heading_path: ["Intro"], token_count: 42,
      page_start: 0, page_end: 0, text: "Hello world", text_truncated: false, context: "", generated_meta: {},
    }],
    chunks_truncated: false,
    vector_set_count: 1,
    cost: { prompt_tokens: 0, completion_tokens: 0, cost_usd: null, priced_call_count: 0 },
    trace: [{
      node_id: "parse", kind: "docling", status: "success", duration_ms: 120, depth: 0,
      node_path: "parse", parent_path: null, item_index: null, score: null, error_type: null, error_message: null,
    }],
    warnings: [],
    failed_node_id: null,
    failed_node_kind: null,
    error: null,
  },
};

const failedResult: PreviewJobResult = { preview_id: "p-2", status: "failed", result: null, error: "ValueError: boom" };

function renderPanel() {
  return render(<PipelinePreviewPanel collectionId="col-1" blob={blob} />);
}

async function switchToUploadAndRun(fileName: string) {
  fireEvent.click(screen.getByRole("button", { name: "Upload a file" }));
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["content"], fileName, { type: "application/pdf" });
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: /run preview/i }));
}

describe("PipelinePreviewPanel", () => {
  it("renders the dry-run report once the job settles as done", async () => {
    vi.mocked(queryDocuments).mockResolvedValue({ total: 0, limit: 8, offset: 0, rows: [] });
    vi.mocked(submitPreviewJob).mockResolvedValue({ preview_id: "p-1", status: "pending" });
    vi.mocked(getPreviewJob).mockResolvedValue(doneResult);
    renderPanel();

    await switchToUploadAndRun("sample.pdf");

    await waitFor(() => expect(screen.getByText("sample.pdf")).toBeInTheDocument());
    expect(screen.getByText("ok")).toBeInTheDocument();
    expect(screen.getByText("Hello world")).toBeInTheDocument();
    expect(screen.getByText("parse")).toBeInTheDocument();
  });

  it("renders the failure reason when the worker job itself fails", async () => {
    vi.mocked(queryDocuments).mockResolvedValue({ total: 0, limit: 8, offset: 0, rows: [] });
    vi.mocked(submitPreviewJob).mockResolvedValue({ preview_id: "p-2", status: "pending" });
    vi.mocked(getPreviewJob).mockResolvedValue(failedResult);
    renderPanel();

    await switchToUploadAndRun("bad.pdf");

    await waitFor(() => expect(screen.getByText("boom")).toBeInTheDocument());
  });
});
