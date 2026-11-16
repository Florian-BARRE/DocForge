// ====== Code Summary ======
// Structure guard of the navigation channel (R-34). Navigation is reached through `useNavigate()`
// (shell/navigation.tsx); the `onNavigate` prop survives ONLY at the route-table boundary: the
// routed entry pages (the pages src/routes.tsx renders), the always-mounted chrome App.tsx hands
// it to (Sidebar, CommandPalette), and the few hooks/builders those entries call with it. A new
// `onNavigate` anywhere else is prop-drilling creeping back: use `useNavigate()` there instead.

import { describe, expect, it } from "vitest";

/** The files allowed to mention `onNavigate`, relative to src/. */
const ALLOWED = new Set([
  // composition root + route table
  "App.tsx",
  "routes.tsx",
  "shell/view.ts",
  // routed entry pages (props pinned by App.routing.characterization.test.tsx)
  "features/auth/KeyDetailPage.tsx",
  "features/auth/SettingsPage.tsx",
  "features/collections/CollectionDetailPage.tsx",
  "features/collections/CollectionOverview.tsx",
  "features/collections/CollectionPipelinePage.tsx",
  "features/collections/CollectionSearchPage.tsx",
  "features/collections/CollectionShell.tsx",
  "features/collections/CollectionsPage.tsx",
  "features/collections/ImportCollectionPage.tsx",
  "features/collections/settings/CollectionSettingsPage.tsx",
  "features/collections/wizard/CollectionWizard.tsx",
  "features/corpus/CorpusPage.tsx",
  "features/explorer/DocumentPage.tsx",
  "features/home/HomePage.tsx",
  "features/jobs/ActivityPage.tsx",
  "features/jobs/CollectionActivityTab.tsx",
  "features/jobs/JobDetailPage.tsx",
  "features/jobs/WorkersPanel.tsx",
  "features/search/SearchLabPage.tsx",
  // hooks/builders an entry calls with its own prop
  "features/collections/wizard/useWizardSubmit.ts",
  "features/corpus/useCorpusPage.ts",
  // always-mounted chrome
  "shell/sidebar/Sidebar.tsx",
  "shell/command-palette/CommandPalette.tsx",
  "shell/command-palette/CommandPaletteDialog.tsx",
  "shell/command-palette/commandItems.ts",
]);

const sources = import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.*"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("navigation channel", () => {
  it("scans the source tree", () => {
    expect(Object.keys(sources).length).toBeGreaterThan(100);
  });

  it("keeps the onNavigate prop at the route-table boundary only", () => {
    const offenders = Object.entries(sources)
      .filter(([, source]) => source.includes("onNavigate"))
      .map(([path]) => path.replace(/^\.\//, ""))
      .filter((path) => !ALLOWED.has(path));
    expect(offenders).toEqual([]);
  });

  it("lists no allowed file that no longer mentions onNavigate", () => {
    const stale = [...ALLOWED].filter((path) => !sources[`./${path}`]?.includes("onNavigate"));
    expect(stale).toEqual([]);
  });
});
