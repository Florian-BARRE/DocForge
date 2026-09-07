// ====== Code Summary ======
// Render smoke-test for the trace tree (JobEventItem stacked, as JobDetailPage renders it): a mix
// of a root stage, a nested group child, a ForEach item instance, a scored node, and a legacy row
// with every new execution-tree column null — asserts the tree + a score chip render without
// throwing (the repro shape for the Phase 1 execution-trace feature). Also covers Phase 2's
// expandable node detail: a node with a shape summary + a fetchable full payload (getEventPayload
// mocked) renders its "Load output" button and, once clicked, the fetched payload; a node with no
// captured trace data at all shows no expand toggle.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JobEvent, JobEventPayload } from "../../api/jobs";
import * as jobsApi from "../../api/jobs";
import { JobEventItem } from "./JobEventItem";

const JOB_ID = "job-1234";

function eventFixture(overrides: Partial<JobEvent>): JobEvent {
  return {
    stage: "parse", status: "success", node_kind: "action",
    started_at: "2026-01-01T00:00:00.000Z", finished_at: "2026-01-01T00:00:01.500Z",
    detail: null, prompt_tokens: null, completion_tokens: null, cost_usd: null,
    score: null, node_path: null, depth: null, parent_path: null, item_index: null,
    event_id: "event-0", input_summary: null, output_summary: null,
    has_full_input: null, has_full_output: null,
    ...overrides,
  };
}

const TRACE: JobEvent[] = [
  // Root stage, scored (e.g. the parser's docling/granite quality score).
  eventFixture({
    stage: "parse", status: "success", node_path: "parse", depth: 0, parent_path: null,
    score: 0.82,
  }),
  // A nested group child under enrich (depth 1) — not scored.
  eventFixture({
    stage: "classify", status: "success", node_kind: "action", node_path: "enrich.classify", depth: 1,
    parent_path: "enrich", score: null,
  }),
  // A ForEach item instance two levels deep, itself scored (e.g. a per-figure VLM call).
  eventFixture({
    stage: "vlm", status: "success", node_kind: "vlm", node_path: "enrich.figures.figbody[0].vlm",
    depth: 2, parent_path: "enrich.figures.figbody", item_index: 0, score: 0.64,
  }),
  // A legacy row written before the execution-tree columns landed — every new field is null.
  eventFixture({ stage: "embed", status: "success" }),
];

describe("JobEventItem (trace tree)", () => {
  it("renders a root + nested + ForEach-item mix with score chips, without throwing", () => {
    render(
      <div>
        {TRACE.map((event, index) => (
          <JobEventItem key={index} event={event} jobId={JOB_ID} />
        ))}
      </div>,
    );

    // Every stage label renders (nested + legacy alike) — humanized via stageLabels.ts.
    expect(screen.getByText("Parsing")).toBeInTheDocument();
    expect(screen.getByText("Classify")).toBeInTheDocument();
    expect(screen.getByText("Vlm")).toBeInTheDocument();
    expect(screen.getByText("Embedding")).toBeInTheDocument();
    // Scored nodes show their score, unscored/legacy nodes don't crash on a null score.
    expect(screen.getByText("score 0.82")).toBeInTheDocument();
    expect(screen.getByText("score 0.64")).toBeInTheDocument();
    // The ForEach item instance surfaces its item index.
    expect(screen.getByText("item[0]")).toBeInTheDocument();
  });

  it("has no expand toggle for a legacy row with no captured trace data", () => {
    render(<JobEventItem event={eventFixture({ stage: "embed", status: "success" })} jobId={JOB_ID} />);
    expect(screen.queryByLabelText("Expand node detail")).not.toBeInTheDocument();
  });

  it("expands a node with a shape summary + lazily fetches its full output payload", async () => {
    const payload: JobEventPayload = {
      job_id: JOB_ID, event_id: "event-parse", slot: "output", stage: "parse", node_path: "parse",
      truncated: false, size_bytes: 42, payload: { blocks: 3 },
    };
    const getEventPayloadSpy = vi.spyOn(jobsApi, "getEventPayload").mockResolvedValue(payload);

    render(
      <JobEventItem
        event={eventFixture({
          stage: "parse", status: "success", node_path: "parse", depth: 0, event_id: "event-parse",
          output_summary: { type: "DocumentIR", fields: 5, hash: "abcdef0123456789abcdef" },
          has_full_output: true,
        })}
        jobId={JOB_ID}
      />,
    );

    // Collapsed by default — no summary/button visible yet.
    expect(screen.queryByText(/output shape/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Expand node detail"));

    // The shape summary is always shown once expanded, no fetch required.
    expect(screen.getByText(/output shape/)).toBeInTheDocument();
    expect(screen.getByText(/type:/)).toBeInTheDocument();

    // The full payload is lazy — never fetched until the button is clicked.
    expect(getEventPayloadSpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Load output" }));
    expect(getEventPayloadSpy).toHaveBeenCalledWith(JOB_ID, "event-parse", "output");

    await waitFor(() => expect(screen.getByText(/"blocks": 3/)).toBeInTheDocument());
  });

  it("shows a dim 'no full payload' state when the fetch 404s despite has_full_output", async () => {
    const { HttpError } = await import("../../api/http");
    vi.spyOn(jobsApi, "getEventPayload").mockRejectedValue(new HttpError(404, [{ message: "not found" }]));

    render(
      <JobEventItem
        event={eventFixture({
          stage: "parse", status: "success", event_id: "event-parse",
          has_full_output: true,
        })}
        jobId={JOB_ID}
      />,
    );

    fireEvent.click(screen.getByLabelText("Expand node detail"));
    fireEvent.click(screen.getByRole("button", { name: "Load output" }));

    await waitFor(() => expect(screen.getByText("no full payload captured")).toBeInTheDocument());
  });
});
