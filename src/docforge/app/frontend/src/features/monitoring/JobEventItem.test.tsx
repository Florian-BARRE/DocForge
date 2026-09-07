// ====== Code Summary ======
// Render smoke-test for the trace tree (JobEventItem stacked, as JobDetailPage renders it): a mix
// of a root stage, a nested group child, a ForEach item instance, a scored node, and a legacy row
// with every new execution-tree column null — asserts the tree + a score chip render without
// throwing (the repro shape for the Phase 1 execution-trace feature).

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { JobEvent } from "../../api/jobs";
import { JobEventItem } from "./JobEventItem";

function eventFixture(overrides: Partial<JobEvent>): JobEvent {
  return {
    stage: "parse", status: "success", node_kind: "action",
    started_at: "2026-01-01T00:00:00.000Z", finished_at: "2026-01-01T00:00:01.500Z",
    detail: null, prompt_tokens: null, completion_tokens: null, cost_usd: null,
    score: null, node_path: null, depth: null, parent_path: null, item_index: null,
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
          <JobEventItem key={index} event={event} />
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
});
