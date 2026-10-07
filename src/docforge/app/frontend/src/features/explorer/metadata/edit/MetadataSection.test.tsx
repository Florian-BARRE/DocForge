// ====== Code Summary ======
// Render smoke-test for MetadataSection on its loading→loaded transition (the schema arrives async,
// so a hook placed after a conditional return would only throw once it re-renders): 0 editable fields
// (no Edit affordance) and N fields (edit → change one value → PATCH carries ONLY that change → live
// re-embed chip). Plus the pure 422 → per-field mapping.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { FieldSpec } from "../../../../api/collections";
import type { MetadataValue } from "../../../../api/explorer";
import { mapFieldErrors } from "./metadataDraft";
import { MetadataSection } from "./MetadataSection";

vi.mock("../../../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../api/collections")>()),
  getCollection: vi.fn(),
}));
vi.mock("../../../../api/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../api/documents")>()),
  updateDocumentMetadata: vi.fn(),
}));
vi.mock("../../../../api/jobs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../../api/jobs")>()),
  getJob: vi.fn(),
}));

const { getCollection } = await import("../../../../api/collections");
const { updateDocumentMetadata } = await import("../../../../api/documents");
const { getJob } = await import("../../../../api/jobs");

function spec(name: string, overrides: Partial<FieldSpec> = {}): FieldSpec {
  return {
    field_name: name, field_type: "string", required: false, filterable: false, lexical: false,
    semantic: false, enum_values: null, origin: "user", scope: "document", description: null, ...overrides,
  };
}

const metadata: MetadataValue[] = [
  { field_name: "summary", value: "old", origin: "generated" },
  { field_name: "year", value: 2020, origin: "user" },
];

function mountWith(fields: FieldSpec[]) {
  vi.mocked(getCollection).mockResolvedValue({ fields } as never);
  return render(<MetadataSection documentId="doc-1" collectionId="col-1" metadata={metadata} onNavigate={vi.fn()} onSaved={vi.fn()} />);
}

describe("MetadataSection", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows no edit affordance when the schema has 0 editable fields", async () => {
    mountWith([spec("chunk_tag", { scope: "chunk" }), spec("sys", { origin: "system" })]);
    await waitFor(() => expect(getCollection).toHaveBeenCalled());
    expect(screen.queryByText("Edit values")).not.toBeInTheDocument();
  });

  it("edits N fields, PATCHes only the change and tracks the re-embed job", async () => {
    vi.mocked(updateDocumentMetadata).mockResolvedValue({ updated_fields: ["summary"], reembedding: true, reembed_fields: ["summary"], job_id: "job-1" });
    vi.mocked(getJob).mockResolvedValue({ status: "running" } as never);
    mountWith([spec("summary", { origin: "generated", semantic: true }), spec("year", { field_type: "integer" })]);

    fireEvent.click(await screen.findByText("Edit values"));
    expect(screen.getByText(/overwritten on the next reingest/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/summary/), { target: { value: "new" } });
    fireEvent.click(screen.getByText("Save changes"));

    await waitFor(() => expect(updateDocumentMetadata).toHaveBeenCalledWith("doc-1", { summary: "new" }));
    expect(await screen.findByText(/re-embedding metadata/)).toBeInTheDocument();
  });
});

describe("mapFieldErrors", () => {
  it("attributes quoted-field messages and keeps the rest general", () => {
    const { byField, general } = mapFieldErrors(["unknown field 'x'", "boom"], ["x", "y"]);
    expect(byField).toEqual({ x: "unknown field 'x'" });
    expect(general).toEqual(["boom"]);
  });
});
