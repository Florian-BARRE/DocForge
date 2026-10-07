// ====== Code Summary ======
// Edit-mode schema save safety: the wizard dry-runs the PATCH first; a destructive schema_diff opens
// the confirmation dialog (confirm sends the real PATCH, cancel writes nothing); a harmless one saves
// directly with no dialog; a renamed row is sent as a `field_ops` rename instead of remove + add.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as collectionsApi from "../../../api/collections";
import type { Collection, SchemaDiff, UpdateCollectionResponse } from "../../../api/collections";
import { ToastProvider } from "../../../shell/toast";
import { CollectionWizard } from "./CollectionWizard";

const FIELD = {
  field_type: "string" as const, required: false, filterable: false, lexical: false, semantic: false,
  enum_values: null, origin: "user" as const, scope: "document" as const, description: null,
};

const COLLECTION: Collection = {
  id: "col-1", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, estimate_overrides: null, trace_verbosity: "shape", title_field: null, tags: [],
  fields: [{ ...FIELD, field_name: "author" }, { ...FIELD, field_name: "year" }],
};

function respond(diff: SchemaDiff, dryRun: boolean): UpdateCollectionResponse {
  return { ...COLLECTION, dry_run: dryRun, schema_diff: diff };
}

function mockApi(diff: SchemaDiff) {
  vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue({ properties: {}, required: [] });
  vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([]);
  return vi.spyOn(collectionsApi, "updateCollection").mockImplementation(
    async (_id, request) => respond(diff, request.dry_run === true),
  );
}

async function walkToSave(editFields: () => void) {
  render(<ToastProvider><CollectionWizard mode="edit" initial={COLLECTION} collectionId="col-1" onNavigate={vi.fn()} /></ToastProvider>);
  fireEvent.click(await screen.findByRole("button", { name: /Next — schema/ }));
  editFields();
  fireEvent.click(screen.getByRole("button", { name: /Next — review/ }));
  fireEvent.click(screen.getByRole("button", { name: /Save changes/ }));
}

afterEach(() => vi.restoreAllMocks());

describe("CollectionWizard — destructive schema save", () => {
  it("opens the dialog on a removal and only the confirm sends the real PATCH", async () => {
    const update = mockApi({ removed: ["year"], values_lost: { year: 7 }, reindex_required_fields: ["author"] });
    await walkToSave(() => fireEvent.click(screen.getByRole("button", { name: "Remove year" })));

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("year");
    expect(dialog).toHaveTextContent("7");
    expect(update).toHaveBeenCalledTimes(1);
    expect(update.mock.calls[0][1].dry_run).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Delete values and save/ }));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(update.mock.calls[1][1].dry_run).toBeUndefined();
  });

  it("cancel writes nothing", async () => {
    const update = mockApi({ removed: ["year"], values_lost: { year: 7 } });
    await walkToSave(() => fireEvent.click(screen.getByRole("button", { name: "Remove year" })));

    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("saves directly, with no dialog, when nothing is destructive", async () => {
    const update = mockApi({ modified: [{ field_name: "author", changed_attrs: ["filterable"] }] });
    await walkToSave(() => {});

    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(update.mock.calls[0][1].dry_run).toBe(true);
    expect(update.mock.calls[1][1].dry_run).toBeUndefined();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("sends a renamed row as a field_ops rename, not remove + add", async () => {
    const update = mockApi({ renamed: [{ from_name: "year", to_name: "published" }] });
    await walkToSave(() => fireEvent.change(screen.getByDisplayValue("year"), { target: { value: "published" } }));

    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    const real = update.mock.calls[1][1];
    expect(real.fields).toBeUndefined();
    expect(real.field_ops).toEqual([{ op: "rename", field_name: "year", new_name: "published" }]);
  });
});
