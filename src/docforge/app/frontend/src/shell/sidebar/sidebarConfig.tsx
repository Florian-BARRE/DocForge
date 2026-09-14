// ====== Code Summary ======
// The global nav's data model — a FLAT list of deployment-scope destinations (no more two-level
// section/page tree: Create/Import/health-presets live inside their own page's toolbar now, not as
// sidebar sub-items). Collection-scoped views (the ones CollectionShell itself owns — `collection`,
// `collection-documents`, `document`, `job`, etc.) intentionally match none of these predicates, so
// no item is HARD-active while inside a specific collection — but `isCollectionScopedView` still lets
// the Collections item SOFT-highlight for a "where am I" cue.

import type { ReactNode } from "react";
import type { View } from "../view";
import { ActivityGlyph, CollectionsGlyph, FleetGlyph, HomeGlyph, SettingsGlyph } from "./icons";

export interface SidebarPage {
  key: string;
  label: string;
  icon: ReactNode;
  view: View;
  isActive: (view: View) => boolean;
}

export const SIDEBAR_PAGES: SidebarPage[] = [
  {
    key: "overview", label: "Overview", icon: <HomeGlyph />,
    view: { name: "overview" },
    isActive: (v) => v.name === "overview",
  },
  {
    key: "collections", label: "Collections", icon: <CollectionsGlyph />,
    view: { name: "collections" },
    isActive: (v) => v.name === "collections" || v.name === "new-collection" || v.name === "import-collection",
  },
  {
    key: "activity", label: "Activity", icon: <ActivityGlyph />,
    view: { name: "activity" },
    isActive: (v) => v.name === "activity",
  },
  {
    key: "fleet", label: "Fleet", icon: <FleetGlyph />,
    view: { name: "fleet" },
    isActive: (v) => v.name === "fleet",
  },
  {
    key: "settings", label: "Settings", icon: <SettingsGlyph />,
    view: { name: "settings" },
    isActive: (v) => v.name === "settings" || v.name === "api-key",
  },
];

/** The active page's key, or null while inside a non-global-nav (collection-scoped/entity) view. */
export function activeSidebarKey(view: View): string | null {
  return SIDEBAR_PAGES.find((page) => page.isActive(view))?.key ?? null;
}

/** Views owned by CollectionShell once you're "inside" one specific collection (its detail tabs or
 *  a document) — none of these match any page's `isActive`, so Collections would otherwise go fully
 *  inert while browsing one. Job detail is intentionally excluded — it's equally reachable from the
 *  fleet-wide Activity page, so it stays neutral rather than claiming Collections.
 *
 *  Realigned for the collection-scope view rename (`collection-metadata` -> `collection-schema`,
 *  `collection-edit` -> `collection-settings`, `collection-pipeline`/`collection-search-pipeline` ->
 *  `collection-pipelines`, `collection-jobs` -> `collection-activity`) — see `shell/view.ts`. */
const COLLECTION_SCOPED_VIEW_NAMES: ReadonlySet<View["name"]> = new Set([
  "collection", "collection-schema", "collection-settings", "collection-pipelines",
  "collection-search", "collection-activity", "collection-documents", "document",
]);

/** Whether the view sits inside a specific collection — drives a SOFT (steel, not forge) highlight
 * on the Collections item so the sidebar keeps a "where am I" cue without claiming a specific page
 * as hard-active. */
export function isCollectionScopedView(view: View): boolean {
  return COLLECTION_SCOPED_VIEW_NAMES.has(view.name);
}
