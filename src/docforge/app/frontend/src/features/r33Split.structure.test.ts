// ====== Code Summary ======
// Structure + model guard of the R-33 split (view + hook + pure model): the eight oversized
// components/hooks stay within the 400-line budget, the pure models stay React-free, and the
// models' key maths behave as the former inline code did.

import { describe, expect, it } from "vitest";
import { DEFAULT_LIMIT, isFirstRunEmptyOf, showSelectAllPromptOf, sortOf } from "./corpus/corpusPageModel";
import { lastFlexColumnIndexOf, orderAfterDrop, orderAfterStep, tableWidthOf } from "./corpus/tableLayoutModel";
import { activeIndexAt, notchPercent, scrollTopForTarget, snapIndexAt } from "./explorer/layout/scrubberModel";
import { activeChunkIdOf, toggleSelection } from "./explorer/layout/pageGroupModel";
import { deriveJobProgress, toMonotonicTimeline, upsertEvent } from "./monitoring/state/jobDetailModel";
import { QUERY_ANCHOR_ID, RERANK_ANCHOR_ID, hasRailNode } from "./search-pipeline/state/searchRailModel";
import * as searchEditor from "./search-pipeline/state/useSearchPipelineEditor";

const MAX_LINES = 400;
const sources = import.meta.glob(
  [
    "./explorer/layout/{PageScrubber,PageGroupRow,scrubberModel,pageGroupModel}.{ts,tsx}",
    "./explorer/layout/{usePageScrubber,usePageGroupRow}.ts",
    "./stage-rail/state/{useStageRailPage,useStageDebouncedApply,stageRailActions}.ts",
    "./search-pipeline/state/{useSearchPipelineEditor,useSearchInspectLoop,searchRailModel}.ts",
    "./corpus/{CorpusPage,CorpusTable,CorpusTableBody,SelectionBanner}.tsx",
    "./corpus/{useCorpusPage,useCorpusTableLayout,corpusPageModel,tableLayoutModel}.ts",
    "./explorer/DocumentPage.tsx",
    "./explorer/state/{useDocumentPage,documentPageModel}.ts",
    "./monitoring/state/{useJobDetail,useJobFeed,jobDetailModel}.ts",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

describe("R-33 split modules", () => {
  it("finds the split modules", () => {
    expect(Object.keys(sources).length).toBeGreaterThanOrEqual(25);
  });

  it.each(Object.entries(sources))("%s stays within the line budget", (_path, source) => {
    expect(source.split("\n").length).toBeLessThanOrEqual(MAX_LINES);
  });

  it.each(Object.entries(sources).filter(([path]) => /Model\.ts$/.test(path)))("%s imports no React", (_path, source) => {
    expect(source).not.toMatch(/from "react"/);
  });

  it("keeps the search anchors importable from the editor hook", () => {
    expect(searchEditor.RERANK_ANCHOR_ID).toBe(RERANK_ANCHOR_ID);
    expect(searchEditor.QUERY_ANCHOR_ID).toBe(QUERY_ANCHOR_ID);
  });
});

describe("scrubberModel", () => {
  it("places notches and snaps the pointer to the nearest one", () => {
    expect(notchPercent(0, 1)).toBe(0);
    expect(notchPercent(1, 3)).toBe(50);
    expect(snapIndexAt(150, 100, 100, 5)).toBe(2);
    expect(snapIndexAt(-50, 100, 100, 5)).toBe(0);
    expect(snapIndexAt(900, 100, 100, 5)).toBe(4);
  });

  it("finds the active page from cached offsets", () => {
    expect(activeIndexAt([0, 100, 300], 150)).toBe(1);
    expect(activeIndexAt([200, 300], 50)).toBe(0);
    expect(scrollTopForTarget(10, 130, 100)).toBe(16);
  });
});

describe("pageGroupModel", () => {
  it("toggles a selection off when the same item is clicked again", () => {
    const first = toggleSelection(null, "block", "b1");
    expect(first).toEqual({ kind: "block", id: "b1" });
    expect(toggleSelection(first, "block", "b1")).toBeNull();
    expect(toggleSelection(first, "chunk", "b1")).toEqual({ kind: "chunk", id: "b1" });
  });

  it("derives the active chunk from the selected chunk or block", () => {
    const chunk = { id: "c1" } as never;
    const byBlock = new Map([["b1", chunk]]);
    expect(activeChunkIdOf({ kind: "chunk", id: "c9" }, byBlock)).toBe("c9");
    expect(activeChunkIdOf({ kind: "block", id: "b1" }, byBlock)).toBe("c1");
    expect(activeChunkIdOf(null, byBlock)).toBeNull();
  });
});

describe("corpus models", () => {
  it("maps sorting and empty/selection flags", () => {
    expect(sortOf([])).toBeNull();
    expect(sortOf([{ id: "created_at", desc: true }])?.direction).toBe("desc");
    expect(DEFAULT_LIMIT).toBe(100);
    expect(showSelectAllPromptOf("ids", true, 250, 100)).toBe(true);
    expect(showSelectAllPromptOf("filtered", true, 250, 100)).toBe(false);
    expect(isFirstRunEmptyOf({ loading: false, error: null, total: 0 }, false)).toBe(true);
    expect(isFirstRunEmptyOf({ loading: false, error: null, total: 0 }, true)).toBe(false);
  });

  it("computes the table width and column reorders", () => {
    expect(tableWidthOf(500, 700)).toBe(1100);
    expect(tableWidthOf(1400, 700)).toBe(1400);
    expect(orderAfterDrop(["a", "b", "c"], "a", "c", "after")).toEqual(["b", "c", "a"]);
    expect(orderAfterDrop(["a", "b", "c"], "c", "a", "before")).toEqual(["c", "a", "b"]);
    expect(orderAfterStep(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(orderAfterStep(["a", "b"], "a", -1)).toBeNull();
    expect(lastFlexColumnIndexOf([])).toBe(-1);
  });
});

describe("jobDetailModel", () => {
  const event = (stage: string, status: string, started_at: string | null) =>
    ({ stage, status, started_at, finished_at: null }) as never;

  it("upserts events by stage", () => {
    const next = upsertEvent([event("parse", "running", "2026-01-01T00:00:00Z")], event("parse", "success", "2026-01-01T00:00:00Z"));
    expect(next).toHaveLength(1);
    expect((next[0] as { status: string }).status).toBe("success");
  });

  it("forward-corrects a stale running stage once a later one started", () => {
    const timeline = toMonotonicTimeline([
      event("chunk", "running", "2026-01-01T00:00:05Z"),
      event("parse", "running", "2026-01-01T00:00:00Z"),
    ]);
    expect(timeline.map((e) => (e as { status: string }).status)).toEqual(["success", "running"]);
  });

  it("sums the ETA over unfinished stages and totals tokens", () => {
    const job = { status: "running", current_stage: "chunk", total_prompt_tokens: 3, total_completion_tokens: 4 } as never;
    const progress = deriveJobProgress(job, [event("parse", "success", "2026-01-01T00:00:00Z")], { parse: 5, chunk: 7 }, 0);
    expect(progress.etaSeconds).toBe(7);
    expect(progress.totalTokens).toBe(7);
    expect(progress.running).toBe(true);
  });
});

describe("searchRailModel", () => {
  it("detects an anchor among the rail nodes", () => {
    expect(hasRailNode([{ id: "retrieve" }], RERANK_ANCHOR_ID)).toBe(true);
    expect(hasRailNode([], QUERY_ANCHOR_ID)).toBe(false);
  });
});
