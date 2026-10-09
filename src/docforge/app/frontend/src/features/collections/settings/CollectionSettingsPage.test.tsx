// ====== Code Summary ======
// Settings sub-tabs render ONLY their own content: General = the contract wizard + Danger zone (and
// still just that after walking the wizard to its Schema step — no Aliases/History/Transfer hanging
// below); Aliases / History / Transfer each show only their panel. The sub-tab bar (CollectionShell's
// CollectionSubNav) navigates by View `section`. The three panels and the Danger zone are stubbed —
// they have their own tests; this one covers the page's section switching.

import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as collectionsApi from "../../../api/collections";
import type { Collection } from "../../../api/collections";
import { ToastProvider } from "../../../shell/toast";
import type { CollectionSettingsSection } from "../../../shell/view";
import { CollectionShell } from "../CollectionShell";
import { CollectionSettingsPage } from "./CollectionSettingsPage";

vi.mock("./AliasesPanel", () => ({ AliasesPanel: () => <div data-testid="aliases-panel" /> }));
vi.mock("../history/ConfigHistoryPanel", () => ({ ConfigHistoryPanel: () => <div data-testid="history-panel" /> }));
vi.mock("../transfer/ExportPanel", () => ({ ExportPanel: () => <div data-testid="transfer-panel" /> }));
vi.mock("./DangerZone", () => ({ DangerZone: () => <div data-testid="danger-zone" /> }));
vi.mock("../../../api/collectionAliases", () => ({ listCollectionAliases: vi.fn().mockResolvedValue([]) }));

const COLLECTION: Collection = {
  id: "c1", name: "Contracts", supported_formats: ["pdf"], max_file_size_bytes: 1000,
  job_timeout_seconds: null, needs_reindex: false, created_at: "2026-01-01T00:00:00Z",
  pipeline: {}, search: {}, estimate_overrides: null, trace_verbosity: "shape", title_field: null, tags: [],
  fields: [],
};

const PANELS = ["aliases-panel", "history-panel", "transfer-panel"];

function renderSection(section: CollectionSettingsSection, onNavigate = vi.fn()): ReactElement {
  vi.spyOn(collectionsApi, "getCollection").mockResolvedValue(COLLECTION);
  vi.spyOn(collectionsApi, "fetchCollectionContractSchema").mockResolvedValue({ properties: {}, required: [] });
  vi.spyOn(collectionsApi, "listCollections").mockResolvedValue([]);
  const ui = (
    <ToastProvider>
      <CollectionShell collectionId="c1" onNavigate={onNavigate} settingsSection={section}>
        <CollectionSettingsPage collectionId="c1" section={section} onNavigate={onNavigate} />
      </CollectionShell>
    </ToastProvider>
  );
  render(ui);
  return ui;
}

afterEach(() => vi.restoreAllMocks());

describe("CollectionSettingsPage sub-tabs", () => {
  it("General shows the wizard and the Danger zone, and keeps the other sections out after the Schema step", async () => {
    renderSection("general");
    expect(await screen.findByTestId("danger-zone")).toBeInTheDocument();
    PANELS.forEach((id) => expect(screen.queryByTestId(id)).not.toBeInTheDocument());

    fireEvent.click(await screen.findByRole("button", { name: /Next — schema/ }));
    expect(screen.getByRole("button", { name: "+ Add field" })).toBeInTheDocument();
    PANELS.forEach((id) => expect(screen.queryByTestId(id)).not.toBeInTheDocument());
  });

  it.each([
    ["aliases", "aliases-panel"],
    ["history", "history-panel"],
    ["transfer", "transfer-panel"],
  ] as const)("%s shows only its own panel", async (section, panel) => {
    renderSection(section);
    expect(await screen.findByTestId(panel)).toBeInTheDocument();
    PANELS.filter((id) => id !== panel).forEach((id) => expect(screen.queryByTestId(id)).not.toBeInTheDocument());
    expect(screen.queryByTestId("danger-zone")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Next — schema/ })).not.toBeInTheDocument();
  });

  it("the sub-tab bar lists the four sections and navigates by section", async () => {
    const onNavigate = vi.fn();
    renderSection("general", onNavigate);
    const bar = await screen.findByRole("tablist", { name: "Settings sections" });
    expect(bar.querySelectorAll('[role="tab"]')).toHaveLength(4);
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(onNavigate).toHaveBeenCalledWith({ name: "collection-settings", collectionId: "c1", section: "history" });
  });
});
