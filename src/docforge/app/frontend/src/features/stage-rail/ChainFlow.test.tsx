// ====== Code Summary ======
// Render smoke-test for ChainFlow: a multi-step scored chain renders every provider chip plus one
// condition chip per transition (quality threshold when the step carries one, failure-only when it
// doesn't), and a single-step chain renders just its one provider chip with no arrow/condition.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ChainStep, Palette } from "../../api/types";
import { ChainFlow } from "./ChainFlow";

const palette: Palette = {
  families: [
    {
      family: "embed",
      title: "Embed",
      description: "",
      mode: "exclusive",
      nodes: [
        { kind: "bge_m3", node_type: "embed", name: "BGE-M3", summary: "", how_it_works: null, config_schema: { properties: {}, required: [] }, consumes: [], produces: [], error_policy: "fail", unique_in_graph: false, scored: false, switch_fields: {} },
        { kind: "openai_compat", node_type: "embed", name: "OpenAI-compatible", summary: "", how_it_works: null, config_schema: { properties: {}, required: [] }, consumes: [], produces: [], error_policy: "fail", unique_in_graph: false, scored: false, switch_fields: {} },
      ],
    },
  ],
};

describe("ChainFlow", () => {
  it("renders one chip per provider and one condition chip per transition", () => {
    const steps: ChainStep[] = [
      { kind: "bge_m3", config: {}, score_below: 0.5 },
      { kind: "openai_compat", config: {}, score_below: null },
    ];

    render(<ChainFlow steps={steps} family="embed" palette={palette} scored />);

    expect(screen.getByText("BGE-M3")).toBeInTheDocument();
    expect(screen.getByText("OpenAI-compatible")).toBeInTheDocument();
    expect(screen.getByText("[quality < 0.5]")).toBeInTheDocument();
  });

  it("renders a single-step chain as one chip with no arrow", () => {
    const steps: ChainStep[] = [{ kind: "bge_m3", config: {}, score_below: null }];

    render(<ChainFlow steps={steps} family="embed" palette={palette} scored={false} />);

    expect(screen.getByText("BGE-M3")).toBeInTheDocument();
    expect(screen.queryByText("→")).not.toBeInTheDocument();
    expect(screen.queryByText(/\[.*\]/)).not.toBeInTheDocument();
  });

  it("renders nothing for an empty chain", () => {
    const { container } = render(<ChainFlow steps={[]} family="embed" palette={palette} scored={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
