// ====== Code Summary ======
// Characterization (safety net) of App.tsx's routing: records, for every View variant, which page
// renders and with which props — plus the CollectionShell wrapper and ITS props — so the route-table
// refactor (R-34) cannot reroute a view. Every page, the shell chrome (Sidebar, CommandPalette) and
// CollectionShell are replaced by inert stubs that print their own props, so the test pins the
// routing table only (no data fetching, nothing visual). ErrorBoundary, ToastProvider, the hash
// bootstrap and `useUrlSync` stay real.

// ====== Third-Party Library Imports ======
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import { App } from "./App";
import { parseViewFromHash } from "./shell/urlSync";

type StubProps = Record<string, unknown> & { children?: ReactNode; onNavigate?: (view: unknown) => void };

const stubs = vi.hoisted(() => ({
  /** A stand-in page: prints its own non-function props as JSON, renders children, exposes onNavigate. */
  make: (h: typeof import("react").createElement, id: string) =>
    function Stub(props: StubProps) {
      const { children, onNavigate, ...rest } = props;
      return h(
        "div",
        { "data-testid": id, "data-props": JSON.stringify(rest), "data-has-navigate": String(typeof onNavigate === "function") },
        h("button", { type: "button", onClick: () => onNavigate?.({ name: "fleet" }) }, `go-fleet-from-${id}`),
        children,
      );
    },
}));

async function stubFor(...names: Array<[exportName: string, id: string]>) {
  const { createElement: h } = await import("react");
  return Object.fromEntries(names.map(([exportName, id]) => [exportName, stubs.make(h, id)]));
}

vi.mock("./features/home/HomePage", () => stubFor(["HomePage", "HomePage"]));
vi.mock("./features/collections/CollectionsPage", () => stubFor(["CollectionsPage", "CollectionsPage"]));
vi.mock("./features/collections/wizard/CollectionWizard", () => stubFor(["CollectionWizard", "CollectionWizard"]));
vi.mock("./features/collections/ImportCollectionPage", () => stubFor(["ImportCollectionPage", "ImportCollectionPage"]));
vi.mock("./features/collections/CollectionShell", () => stubFor(["CollectionShell", "CollectionShell"]));
vi.mock("./features/collections/CollectionOverview", () => stubFor(["CollectionOverview", "CollectionOverview"]));
vi.mock("./features/collections/CollectionDetailPage", () => stubFor(["CollectionDetailPage", "CollectionDetailPage"]));
vi.mock("./features/collections/settings/CollectionSettingsPage", () =>
  stubFor(["CollectionSettingsPage", "CollectionSettingsPage"]),
);
vi.mock("./features/collections/CollectionSearchPage", () => stubFor(["CollectionSearchPage", "CollectionSearchPage"]));
vi.mock("./features/collections/CollectionPipelinePage", () => stubFor(["CollectionPipelinePage", "CollectionPipelinePage"]));
vi.mock("./features/jobs/CollectionActivityTab", () => stubFor(["CollectionActivityTab", "CollectionActivityTab"]));
vi.mock("./features/corpus/CorpusPage", () => stubFor(["CorpusPage", "CorpusPage"]));
vi.mock("./features/search/SearchLabPage", () => stubFor(["SearchLabPage", "SearchLabPage"]));
vi.mock("./features/explorer/DocumentPage", () => stubFor(["DocumentPage", "DocumentPage"]));
vi.mock("./features/monitoring/JobDetailPage", () => stubFor(["JobDetailPage", "JobDetailPage"]));
vi.mock("./features/jobs/ActivityPage", () => stubFor(["ActivityPage", "ActivityPage"]));
vi.mock("./features/monitoring/WorkersPanel", () => stubFor(["WorkersPanel", "WorkersPanel"]));
vi.mock("./features/auth/SettingsPage", () => stubFor(["SettingsPage", "SettingsPage"]));
vi.mock("./features/auth/KeyDetailPage", () => stubFor(["KeyDetailPage", "KeyDetailPage"]));
vi.mock("./shell/command-palette/CommandPalette", () => stubFor(["CommandPalette", "CommandPalette"]));
vi.mock("./shell/sidebar/Sidebar", async () => ({
  ...(await stubFor(["Sidebar", "Sidebar"])),
  SIDEBAR_EXPANDED_WIDTH: 240,
  SIDEBAR_RAIL_WIDTH: 72,
}));

/** One rendered page: its test id (the component) and its props as JSON. */
interface Rendered {
  id: string;
  props: Record<string, unknown>;
}

/** The routed pages currently on screen, outermost first, excluding the always-mounted chrome. */
function routedChain(): Rendered[] {
  const chrome = new Set(["Sidebar", "CommandPalette"]);
  return Array.from(document.querySelectorAll<HTMLElement>("[data-testid]"))
    .filter((el) => !chrome.has(el.dataset.testid ?? ""))
    .map((el) => ({ id: el.dataset.testid as string, props: JSON.parse(el.dataset.props ?? "{}") }));
}

async function renderAt(hash: string) {
  window.location.hash = hash;
  const utils = render(createElement(App));
  // The lazy routes resolve asynchronously: wait for a routed page to be on screen.
  await waitFor(() => expect(routedChain().length).toBeGreaterThan(0));
  return utils;
}

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "#");
});

afterEach(() => {
  window.history.replaceState(null, "", "#");
});

const C = { collectionId: "c1" };

/** hash -> the chain of routed components with their props (shell first, then its child page). */
const ROUTES: Array<[hash: string, label: string, chain: Rendered[]]> = [
  ["#/overview", "overview", [{ id: "HomePage", props: {} }]],
  ["#/collections", "collections", [{ id: "CollectionsPage", props: {} }]],
  ["#/collections/filter/attention", "collections, attention", [{ id: "CollectionsPage", props: { initialHealthFilter: "attention" } }]],
  ["#/collections/filter/operational", "collections, operational", [{ id: "CollectionsPage", props: { initialHealthFilter: "operational" } }]],
  ["#/collections/filter/empty", "collections, empty", [{ id: "CollectionsPage", props: { initialHealthFilter: "empty" } }]],
  ["#/collections/new", "new-collection", [{ id: "CollectionWizard", props: {} }]],
  ["#/collections/import", "import-collection", [{ id: "ImportCollectionPage", props: {} }]],
  [
    "#/collections/c1",
    "collection",
    [
      { id: "CollectionShell", props: C },
      { id: "CollectionOverview", props: C },
    ],
  ],
  [
    "#/collections/c1/schema",
    "collection-schema",
    [
      { id: "CollectionShell", props: C },
      { id: "CollectionDetailPage", props: C },
    ],
  ],
  [
    "#/collections/c1/settings",
    "collection-settings (default section)",
    [
      { id: "CollectionShell", props: { ...C, settingsSection: "general" } },
      { id: "CollectionSettingsPage", props: { ...C, section: "general" } },
    ],
  ],
  [
    "#/collections/c1/settings/aliases",
    "collection-settings (aliases)",
    [
      { id: "CollectionShell", props: { ...C, settingsSection: "aliases" } },
      { id: "CollectionSettingsPage", props: { ...C, section: "aliases" } },
    ],
  ],
  [
    "#/collections/c1/settings/history",
    "collection-settings (history)",
    [
      { id: "CollectionShell", props: { ...C, settingsSection: "history" } },
      { id: "CollectionSettingsPage", props: { ...C, section: "history" } },
    ],
  ],
  [
    "#/collections/c1/settings/transfer",
    "collection-settings (transfer)",
    [
      { id: "CollectionShell", props: { ...C, settingsSection: "transfer" } },
      { id: "CollectionSettingsPage", props: { ...C, section: "transfer" } },
    ],
  ],
  [
    "#/collections/c1/pipelines/ingestion",
    "collection-pipelines (ingestion)",
    [
      { id: "CollectionShell", props: { ...C, pipelineStage: "ingestion" } },
      { id: "CollectionPipelinePage", props: C },
    ],
  ],
  [
    "#/collections/c1/pipelines/search",
    "collection-pipelines (search)",
    [
      { id: "CollectionShell", props: { ...C, pipelineStage: "search" } },
      { id: "CollectionSearchPage", props: C },
    ],
  ],
  [
    "#/collections/c1/activity",
    "collection-activity",
    [
      { id: "CollectionShell", props: C },
      { id: "CollectionActivityTab", props: C },
    ],
  ],
  [
    "#/collections/c1/documents",
    "collection-documents",
    [
      { id: "CollectionShell", props: C },
      { id: "CorpusPage", props: C },
    ],
  ],
  [
    "#/collections/c1/search",
    "collection-search",
    [
      { id: "CollectionShell", props: C },
      { id: "SearchLabPage", props: C },
    ],
  ],
  [
    "#/collections/c1/documents/d1",
    "document",
    [
      { id: "CollectionShell", props: C },
      { id: "DocumentPage", props: { ...C, documentId: "d1" } },
    ],
  ],
  [
    "#/collections/c1/jobs/j1",
    "job",
    [
      { id: "CollectionShell", props: C },
      { id: "JobDetailPage", props: { ...C, jobId: "j1" } },
    ],
  ],
  ["#/activity", "activity (jobs tab default)", [{ id: "ActivityPage", props: { tab: "jobs" } }]],
  ["#/activity/failures", "activity (failures)", [{ id: "ActivityPage", props: { tab: "failures" } }]],
  ["#/activity/trends", "activity (trends)", [{ id: "ActivityPage", props: { tab: "trends" } }]],
  ["#/fleet", "fleet", [{ id: "WorkersPanel", props: {} }]],
  ["#/settings", "settings (keys default)", [{ id: "SettingsPage", props: { section: "keys" } }]],
  ["#/settings/audit", "settings (audit)", [{ id: "SettingsPage", props: { section: "audit" } }]],
  ["#/settings/deployment", "settings (deployment)", [{ id: "SettingsPage", props: { section: "deployment" } }]],
  ["#/settings/keys/k1", "api-key", [{ id: "KeyDetailPage", props: { keyId: "k1" } }]],
];

describe("App routing — each View renders the right page with the right props", () => {
  it.each(ROUTES)("%s (%s)", async (hash, _label, chain) => {
    await renderAt(hash);
    expect(routedChain()).toEqual(chain);
  });

  it("covers all 17 View variants of the union", () => {
    const reached = new Set(ROUTES.map(([hash]) => parseViewFromHash(hash).name));
    expect(reached).toEqual(
      new Set([
        "overview", "collections", "new-collection", "import-collection", "collection", "collection-schema",
        "collection-settings", "collection-pipelines", "collection-activity", "collection-documents",
        "collection-search", "document", "job", "activity", "fleet", "settings", "api-key",
      ]),
    );
  });

  it("an empty hash lands on the overview and rewrites the URL to #/overview", async () => {
    await renderAt("");
    expect(routedChain()).toEqual([{ id: "HomePage", props: {} }]);
    expect(window.location.hash).toBe("#/overview");
  });

  it("an unknown hash lands on the overview", async () => {
    await renderAt("#/nope/nothing");
    expect(routedChain()).toEqual([{ id: "HomePage", props: {} }]);
  });

  it("legacy hashes still route (jobs -> activity, workers -> fleet, api-keys -> settings)", async () => {
    await renderAt("#/jobs/failures");
    expect(routedChain()).toEqual([{ id: "ActivityPage", props: { tab: "failures" } }]);
  });
});

describe("App routing — chrome and wiring", () => {
  it("always mounts the Sidebar and the command palette beside the routed page", async () => {
    await renderAt("#/fleet");
    expect(screen.getByTestId("Sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("CommandPalette")).toBeInTheDocument();
  });

  it("hands the current view and an onNavigate to the Sidebar and the palette", async () => {
    await renderAt("#/collections/c1/documents");
    const sidebar = JSON.parse(screen.getByTestId("Sidebar").dataset.props ?? "{}");
    expect(sidebar).toMatchObject({ view: { name: "collection-documents", collectionId: "c1" }, expanded: true });
    expect(screen.getByTestId("Sidebar").dataset.hasNavigate).toBe("true");
    const palette = JSON.parse(screen.getByTestId("CommandPalette").dataset.props ?? "{}");
    expect(palette).toMatchObject({ open: false, view: { name: "collection-documents", collectionId: "c1" } });
  });

  it("gives every routed page a working onNavigate", async () => {
    for (const [hash] of ROUTES) {
      const { unmount } = await renderAt(hash);
      const page = routedChain().at(-1)!;
      expect(screen.getByTestId(page.id).dataset.hasNavigate).toBe("true");
      unmount();
    }
  });

  it.each(ROUTES.map(([hash, label, chain]) => [hash, label, chain.at(-1)!.id] as const))(
    "navigating from %s (%s) swaps the page and pushes the new hash",
    async (hash, _label, leafId) => {
      await renderAt(hash);
      fireEvent.click(screen.getByText(`go-fleet-from-${leafId}`));
      await waitFor(() => expect(routedChain()).toEqual([{ id: "WorkersPanel", props: {} }]));
      expect(window.location.hash).toBe("#/fleet");
    },
  );

  it("follows browser Back/Forward (popstate) through the same router", async () => {
    await renderAt("#/overview");
    act(() => {
      window.history.pushState(null, "", "#/settings/audit");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await waitFor(() => expect(routedChain()).toEqual([{ id: "SettingsPage", props: { section: "audit" } }]));
  });

  it("opens the command palette on Ctrl/Cmd+K without changing the routed page", async () => {
    await renderAt("#/fleet");
    act(() => {
      fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    });
    await waitFor(() =>
      expect(JSON.parse(screen.getByTestId("CommandPalette").dataset.props ?? "{}")).toMatchObject({ open: true }),
    );
    expect(routedChain()).toEqual([{ id: "WorkersPanel", props: {} }]);
  });
});
