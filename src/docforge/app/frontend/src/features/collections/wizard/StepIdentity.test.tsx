// ====== Code Summary ======
// Render smoke-test for the trace-verbosity promotion: `trace_verbosity` must render as a
// first-class `TraceVerbosityField` radiogroup, visible WITHOUT expanding "Show technical
// details" — the exact gap the user flagged (previously only reachable via the generic
// SchemaForm buried under advanced). Also covers that toggling it round-trips through the
// wizard's `extra`/`onExtraChange` overflow bag, same plumbing every other unnamed contract
// field already uses.

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import * as collectionsApi from "../../../api/collections";
import type { Collection } from "../../../api/collections";
import type { JsonSchema } from "../../../api/types";
import { StepIdentity } from "./StepIdentity";

const OTHER_COLLECTION: Collection = {
  id: "col-other", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, fields: [], estimate_overrides: null, trace_verbosity: "shape", tags: [],
};

const SCHEMA: JsonSchema = {
  properties: {
    name: { type: "string", description: "Unique human name." },
    supported_formats: {
      type: "array",
      items: { type: "string" },
      description: "Accepted upload extensions.",
    },
    max_file_size_bytes: { type: "integer", default: 52428800, description: "Upload size ceiling, bytes." },
    job_timeout_seconds: {
      anyOf: [{ type: "number" }, { type: "null" }],
      default: null,
      description: "Per-collection job budget.",
    },
    trace_verbosity: {
      type: "string",
      enum: ["shape", "full"],
      default: "shape",
      description: "Execution-trace capture level: 'shape' keeps only a cheap shape summary.",
    },
    preset: {
      anyOf: [{ type: "string", enum: ["standard", "light"] }, { type: "null" }],
      default: null,
      description: "Stock ingestion blob.",
    },
  },
  required: ["name", "supported_formats", "max_file_size_bytes"],
};

function renderStep(extra: Record<string, unknown>, onExtraChange = vi.fn(), name = "my-collection") {
  return render(
    <StepIdentity
      mode="create"
      name={name} onNameChange={vi.fn()}
      formats={["pdf"]} onFormatsChange={vi.fn()}
      tags={[]} onTagsChange={vi.fn()}
      maxSizeMb={50} onMaxSizeMbChange={vi.fn()}
      jobTimeoutSeconds={null} onJobTimeoutSecondsChange={vi.fn()}
      preset="standard" onPresetChange={vi.fn()}
      extra={extra} onExtraChange={onExtraChange}
      onNext={vi.fn()}
    />,
  );
}

describe("StepIdentity — trace verbosity promotion", () => {
  it("renders the Execution trace radiogroup without expanding 'Show technical details'", async () => {
    vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue(SCHEMA);
    vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([]);

    renderStep({});

    await waitFor(() => expect(screen.getByText("Execution trace")).toBeInTheDocument());
    // Never rendered by the generic SchemaForm — no stray "Trace verbosity" schema-driven label.
    expect(screen.queryByText("Trace verbosity")).not.toBeInTheDocument();
    // "Show technical details" was never clicked — still visible right away.
    expect(screen.queryByText("Show technical details")).toBeInTheDocument();

    const shapeOption = screen.getByRole("radio", { name: /^Summary/ });
    const fullOption = screen.getByRole("radio", { name: /^Full/ });
    expect(shapeOption).toHaveAttribute("aria-checked", "true");
    expect(fullOption).toHaveAttribute("aria-checked", "false");
  });

  it("selects 'full' from the schema default when the draft carries a stored value", async () => {
    vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue(SCHEMA);
    vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([]);

    renderStep({ trace_verbosity: "full" });

    await waitFor(() => expect(screen.getByText("Execution trace")).toBeInTheDocument());
    expect(screen.getByRole("radio", { name: /^Full/ })).toHaveAttribute("aria-checked", "true");
  });

  it("toggling 'Full' round-trips through the extra overflow bag", async () => {
    vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue(SCHEMA);
    vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([]);
    const onExtraChange = vi.fn();

    renderStep({}, onExtraChange);

    await waitFor(() => expect(screen.getByText("Execution trace")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("radio", { name: /^Full/ }));

    expect(onExtraChange).toHaveBeenCalledWith({ trace_verbosity: "full" });
  });
});

describe("StepIdentity — duplicate-name check", () => {
  it("flags a name that collides with an existing collection and disables Next", async () => {
    vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue(SCHEMA);
    vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([OTHER_COLLECTION]);

    renderStep({}, vi.fn(), "Contracts");

    await waitFor(() => expect(screen.getByText(/already exists/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Next — schema" })).toBeDisabled();
  });

  it("does not flag a unique name", async () => {
    vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue(SCHEMA);
    vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([OTHER_COLLECTION]);

    renderStep({}, vi.fn(), "Something else");

    await waitFor(() => expect(screen.getByText("Execution trace")).toBeInTheDocument());
    expect(screen.queryByText(/already exists/)).not.toBeInTheDocument();
  });
});
