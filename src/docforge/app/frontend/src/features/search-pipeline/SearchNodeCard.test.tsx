// ====== Code Summary ======
// Render smoke-test for SearchNodeCard's collapse/expand — the search-pipeline analog of
// StageCard.test.tsx. A configurable node starts expanded (its config field visible); clicking its
// header collapses the body away (replaced by nothing extra here — search nodes have no collapsed
// summary line yet, unlike the ingestion stage rail) and clicking again re-expands it. A read-only
// node (no config fields) gets no collapse affordance at all.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Palette } from "../../api/types";
import { SearchNodeCard } from "./SearchNodeCard";

const palette: Palette = {
  families: [
    {
      family: "encode",
      title: "Encode",
      description: "Encodes the query into vectors.",
      mode: "exclusive",
      nodes: [
        {
          kind: "collection",
          node_type: "action",
          name: "Collection embedder",
          summary: "Embeds the query with the collection's own embedder.",
          how_it_works: null,
          config_schema: {
            // NOT an advanced-tuning name (see advancedFields.ts's keyword list) — stays in the
            // always-rendered "basic" tier, so it's visible immediately without a "Show technical
            // details" toggle click.
            properties: { candidate_multiplier: { type: "integer", default: 8, description: "Over-fetch factor." } },
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
    {
      family: "deliver",
      title: "Deliver",
      description: "Assembles the final search result.",
      mode: "exclusive",
      nodes: [
        {
          kind: "hits",
          node_type: "action",
          name: "Search result",
          summary: "Assembles the final SearchResult payload.",
          how_it_works: null,
          config_schema: { properties: {}, required: [] },
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

describe("SearchNodeCard — collapse/expand", () => {
  it("starts expanded, collapses on header click, and re-expands", () => {
    render(
      <SearchNodeCard
        step={2}
        node={{ node_type: "action", id: "encode", family: "encode", kind: "collection", config: { candidate_multiplier: 8 } }}
        palette={palette}
        onChangeConfig={vi.fn()}
      />,
    );

    expect(screen.getByRole("spinbutton")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Collection embedder/ }));
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Collection embedder/ }));
    expect(screen.getByRole("spinbutton")).toBeInTheDocument();
  });

  it("gives a read-only (no-config) node no collapse affordance", () => {
    render(
      <SearchNodeCard
        step={6}
        node={{ node_type: "action", id: "deliver", family: "deliver", kind: "hits", config: {} }}
        palette={palette}
        onChangeConfig={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Search result/ })).not.toBeInTheDocument();
    expect(screen.getByText("read-only")).toBeInTheDocument();
  });
});
