// ====== Code Summary ======
// Render smoke-test for SearchPipelineMinimap — the search-pipeline analog of
// StageRailMinimap.test.tsx: one numbered entry per step, the active one highlighted, and
// clicking an entry jump-scrolls to its DOM anchor (shared `stageAnchorId` convention).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { stageAnchorId } from "../stage-rail/state/stageAnchor";
import { SearchPipelineMinimap } from "./SearchPipelineMinimap";
import type { SearchMinimapEntry } from "./state/searchMinimapEntries";

const entries: SearchMinimapEntry[] = [
  { key: "normalize", title: "Normalize query", enabled: true },
  { key: "encode", title: "Collection embedder", enabled: true },
  { key: "retrieve", title: "Hybrid search", enabled: true },
  { key: "rerank", title: "Reranking", enabled: false },
];

describe("SearchPipelineMinimap", () => {
  it("renders one entry per step and jump-scrolls the target anchor on click", () => {
    entries.forEach((entry) => {
      const anchor = document.createElement("div");
      anchor.id = stageAnchorId(entry.key);
      anchor.scrollIntoView = vi.fn();
      document.body.appendChild(anchor);
    });

    render(<SearchPipelineMinimap entries={entries} activeKey="retrieve" />);

    expect(screen.getByRole("button", { name: "Normalize query" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reranking" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reranking" }));

    const rerankAnchor = document.getElementById(stageAnchorId("rerank")) as HTMLElement & { scrollIntoView: () => void };
    expect(rerankAnchor.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });
});
