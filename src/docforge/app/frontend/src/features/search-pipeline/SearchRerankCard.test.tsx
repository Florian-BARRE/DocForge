// ====== Code Summary ======
// Reranking card: while off it surfaces the amber ships-off / local-CPU caveat (round-4 T9) and no
// config; while on it renders the rerank node's schema-driven config form (e.g. `base_url`) and
// routes edits through `onChangeConfig`.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ActionBlob, Palette } from "../../api/types";
import { SearchRerankCard } from "./SearchRerankCard";

const palette: Palette = {
  families: [
    {
      family: "rerank",
      title: "Rerank",
      description: "Re-ranks results.",
      mode: "exclusive",
      nodes: [
        {
          kind: "cross_encoder",
          node_type: "action",
          name: "Cross-encoder",
          summary: "Cross-encoder reranker.",
          how_it_works: null,
          config_schema: {
            properties: { base_url: { type: "string", default: "", description: "Reranker endpoint." } },
            required: [],
          },
          consumes: [],
          produces: [],
          error_policy: "fail",
          unique_in_graph: true,
          scored: false,
          switch_fields: {},
        },
      ],
    },
  ],
};

const node: ActionBlob = { node_type: "action", id: "rerank", family: "rerank", kind: "cross_encoder", config: { base_url: "http://old" } };

describe("SearchRerankCard — off-state caveat", () => {
  it("shows the ships-off / local-CPU-not-recommended note and no config while disabled", () => {
    render(<SearchRerankCard step={5} enabled={false} onToggle={vi.fn()} node={node} palette={palette} onChangeConfig={vi.fn()} />);
    expect(screen.getByText(/Provider-hosted — ships off/)).toBeInTheDocument();
    expect(screen.getByText(/local CPU reranker is NOT recommended/)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("http://old")).not.toBeInTheDocument();
  });

  it("shows no caveat once reranking is enabled", () => {
    render(<SearchRerankCard step={5} enabled onToggle={vi.fn()} />);
    expect(screen.queryByText(/ships off/)).not.toBeInTheDocument();
  });
});

describe("SearchRerankCard — config form", () => {
  it("renders the base_url field when enabled and forwards edits", () => {
    const onChangeConfig = vi.fn();
    render(<SearchRerankCard step={5} enabled onToggle={vi.fn()} node={node} palette={palette} onChangeConfig={onChangeConfig} />);
    const input = screen.getByDisplayValue("http://old");
    fireEvent.change(input, { target: { value: "http://new" } });
    expect(onChangeConfig).toHaveBeenCalledWith("base_url", "http://new");
  });
});
