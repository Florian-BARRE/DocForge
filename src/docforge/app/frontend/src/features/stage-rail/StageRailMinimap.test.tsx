// ====== Code Summary ======
// Render smoke-test for StageRailMinimap: it renders every stage as a numbered entry, highlights
// the active one, and clicking an entry jump-scrolls to that stage's anchor.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StageView } from "../../api/types";
import { stageAnchorId } from "./state/stageAnchor";
import { StageRailMinimap } from "./StageRailMinimap";

function stageFixture(key: string, title: string): StageView {
  return {
    key, title, description: "", kind: "toggle", enabled: true, removable: true,
    family: null, provider: null, available: [], config: {}, chains: [], stack: [], requires: [], notes: null,
  };
}

const stages: StageView[] = [stageFixture("parse", "Parse"), stageFixture("chunk", "Chunk"), stageFixture("embed", "Embed")];

describe("StageRailMinimap", () => {
  it("renders one entry per stage and jump-scrolls the target anchor on click", () => {
    // The anchor elements the minimap must resolve by id — StageCard normally supplies these.
    stages.forEach((stage) => {
      const anchor = document.createElement("div");
      anchor.id = stageAnchorId(stage.key);
      anchor.scrollIntoView = vi.fn();
      document.body.appendChild(anchor);
    });

    render(<StageRailMinimap stages={stages} activeKey="chunk" />);

    expect(screen.getByRole("button", { name: "Parse" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chunk" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Embed" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Embed" }));

    const embedAnchor = document.getElementById(stageAnchorId("embed")) as HTMLElement & { scrollIntoView: () => void };
    expect(embedAnchor.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
  });
});
