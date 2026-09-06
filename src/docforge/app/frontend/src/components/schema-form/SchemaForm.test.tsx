// ====== Code Summary ======
// Render smoke-test for SchemaForm's real basic/advanced split — the audit's core "the toggle hides
// nothing" complaint. Asserts a tuning-keyword numeric field (`timeout_seconds`) starts hidden and
// only appears once "Show technical details" is clicked, while a decision field (an enum) is always
// visible; and that a schema with no advanced field never grows a dead toggle button.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JsonSchema } from "../../api/types";
import { SchemaForm } from "./SchemaForm";

const schemaWithAdvanced: JsonSchema = {
  properties: {
    method: { type: "string", enum: ["fast", "accurate"], default: "fast", description: "How to run it." },
    timeout_seconds: { type: "number", default: 30, description: "Per-request timeout." },
  },
  required: [],
};

const schemaAllBasic: JsonSchema = {
  properties: {
    method: { type: "string", enum: ["fast", "accurate"], default: "fast", description: "How to run it." },
  },
  required: [],
};

describe("SchemaForm — basic/advanced progressive disclosure", () => {
  it("hides a tuning-keyword numeric field until 'Show technical details' is clicked", () => {
    render(<SchemaForm schema={schemaWithAdvanced} values={{ method: "fast", timeout_seconds: 30 }} onChange={vi.fn()} />);

    expect(screen.getByText("Method")).toBeInTheDocument();
    // "timeout_seconds" is curated by fieldLabels.ts as "Request timeout" — it must still be findable
    // by that label even hidden, so assert absence by that exact text, not a guess at the raw name.
    expect(screen.queryByText("Request timeout")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Show technical details"));

    expect(screen.getByText("Request timeout")).toBeInTheDocument();
    expect(screen.getByText("Hide technical details")).toBeInTheDocument();
  });

  it("renders no toggle button when the schema has no advanced field", () => {
    render(<SchemaForm schema={schemaAllBasic} values={{ method: "fast" }} onChange={vi.fn()} />);

    expect(screen.getByText("Method")).toBeInTheDocument();
    expect(screen.queryByText("Show technical details")).not.toBeInTheDocument();
  });
});
