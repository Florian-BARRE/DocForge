// ====== Code Summary ======
// Render smoke-test for StageCard's collapse/expand — the audit's "4500px wall" fix. An enabled
// provider stage starts expanded (today's default); clicking its header collapses the body away
// (the config form disappears, a one-line summary takes its place) and clicking again re-expands it.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Palette, StageView } from "../../api/types";
import type { StageRailActions } from "./actions";
import { StageCard } from "./StageCard";

const palette: Palette = {
  families: [
    {
      family: "chunker",
      title: "Chunker",
      description: "Splits the IR into retrieval chunks.",
      mode: "exclusive",
      nodes: [
        {
          kind: "fixed_size",
          node_type: "chunk",
          name: "Fixed size",
          summary: "Splits by a fixed token window.",
          how_it_works: null,
          config_schema: {
            properties: { chunk_size: { type: "integer", default: 512, description: "Tokens per chunk." } },
            required: [],
          },
          consumes: [],
          produces: [],
          error_policy: "fail",
          unique_in_graph: false,
          scored: false,
          switch_fields: {},
        },
      ],
    },
  ],
};

const stage: StageView = {
  key: "chunk",
  title: "Chunk",
  description: "Split the enriched IR into retrieval chunks with the chosen chunking method.",
  kind: "provider",
  enabled: true,
  removable: false,
  family: "chunker",
  provider: "fixed_size",
  available: ["fixed_size"],
  config: { chunk_size: 512 },
  chains: [],
  stack: [],
  requires: [],
  notes: null,
};

const actions: StageRailActions = {
  enableStage: vi.fn(),
  disableStage: vi.fn(),
  setProvider: vi.fn(),
  setConfig: vi.fn(),
  setStackSteps: vi.fn(),
  setStackMethodConfig: vi.fn(),
  setChainSteps: vi.fn(),
  setChainStepConfig: vi.fn(),
  setChainStepScoreBelow: vi.fn(),
  setStackMethodChainSteps: vi.fn(),
  setStackMethodChainStepConfig: vi.fn(),
};

describe("StageCard — collapse/expand", () => {
  it("starts expanded, collapses on header click (hiding the body), and re-expands", () => {
    render(<StageCard stage={stage} palette={palette} actions={actions} />);

    // Expanded: the chunk_size numeric control is on screen, no collapsed one-line summary yet.
    expect(screen.getByRole("spinbutton")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Chunk/ }));

    // Collapsed: the config form is gone, replaced by the one-line provider summary.
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.getByText("Fixed size")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Chunk/ }));

    expect(screen.getByRole("spinbutton")).toBeInTheDocument();
  });

  it("gives a disabled, non-fixed stage no expand affordance", () => {
    render(<StageCard stage={{ ...stage, enabled: false, removable: true }} palette={palette} actions={actions} />);
    expect(screen.queryByRole("button", { name: /Chunk/ })).not.toBeInTheDocument();
  });
});
