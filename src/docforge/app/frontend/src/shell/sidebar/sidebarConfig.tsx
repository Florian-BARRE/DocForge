// ====== Code Summary ======
// The global nav tree's data model — sections → pages, each carrying its destination View and an
// `isActive` predicate. Mirrors the data-driven SECTION_ORDER/SUBTABS pattern already used by
// CollectionShell's two-level tabs, but for GLOBAL navigation: collection-scoped views (the ones
// CollectionShell itself owns — `collection`, `collection-documents`, `document`, `job`, etc.)
// intentionally match none of these predicates, so no page/section is HARD-active while inside a
// specific collection (that in-collection nav stays CollectionShell's job, not this one's) — but
// `isCollectionScopedView` still lets the Collections section SOFT-highlight for a "where am I" cue.
//
// No health-preset pages here on purpose: the fleet's own toolbar (CollectionsToolbar, "Needs
// attention"/"Empty"/"Operational") is the single source of truth for health filtering — the
// sidebar just deep-links into it via the still-live `{name:"collections", health}` View field
// (see shell/urlSync.ts + CollectionsPage's `initialHealthFilter`), it no longer duplicates it.

import type { ReactNode } from "react";
import type { View } from "../view";
import { AdminGlyph, AllGlyph, ApiKeyGlyph, CollectionsGlyph, CreateGlyph, ImportGlyph, WorkersGlyph, WorkersPageGlyph } from "./icons";

export interface SidebarPage {
  key: string;
  label: string;
  icon: ReactNode;
  view: View;
  isActive: (view: View) => boolean;
}

export interface SidebarSection {
  key: string;
  label: string;
  icon: ReactNode;
  pages: SidebarPage[];
}

export const SIDEBAR_SECTIONS: SidebarSection[] = [
  {
    key: "collections",
    label: "Collections",
    icon: <CollectionsGlyph />,
    pages: [
      {
        key: "all", label: "All", icon: <AllGlyph />,
        view: { name: "collections" },
        isActive: (v) => v.name === "collections" && !v.health,
      },
      {
        key: "create", label: "Create", icon: <CreateGlyph />,
        view: { name: "new-collection" },
        isActive: (v) => v.name === "new-collection",
      },
      {
        key: "import", label: "Import", icon: <ImportGlyph />,
        view: { name: "import-collection" },
        isActive: (v) => v.name === "import-collection",
      },
    ],
  },
  {
    key: "workers",
    label: "Workers & Jobs",
    icon: <WorkersGlyph />,
    pages: [
      {
        key: "workers", label: "Workers", icon: <WorkersPageGlyph />,
        view: { name: "workers" },
        isActive: (v) => v.name === "workers",
      },
    ],
  },
  {
    key: "admin",
    label: "Admin",
    icon: <AdminGlyph />,
    pages: [
      {
        key: "api-keys", label: "API Keys", icon: <ApiKeyGlyph />,
        view: { name: "api-keys" },
        isActive: (v) => v.name === "api-keys",
      },
    ],
  },
];

/** The section key owning the view's active page, or null while inside a non-global-nav view. */
export function activeSectionKey(view: View): string | null {
  return SIDEBAR_SECTIONS.find((section) => section.pages.some((page) => page.isActive(view)))?.key ?? null;
}

/** The active page's key within its section, or null while inside a non-global-nav view. */
export function activePageKey(view: View): string | null {
  for (const section of SIDEBAR_SECTIONS) {
    const page = section.pages.find((p) => p.isActive(view));
    if (page) return page.key;
  }
  return null;
}

/** Views owned by CollectionShell once you're "inside" one specific collection (its detail tabs,
 * a document, or a job) — none of these match any page's `isActive`, so the Collections section
 * would otherwise go fully inert. */
const COLLECTION_SCOPED_VIEW_NAMES: ReadonlySet<View["name"]> = new Set([
  "collection", "collection-metadata", "collection-edit", "collection-pipeline",
  "collection-search-pipeline", "collection-jobs", "collection-documents",
  "collection-search", "document", "job",
]);

/** Whether the view sits inside a specific collection — drives a SOFT (steel, not forge) highlight
 * on the Collections section so the sidebar keeps a "where am I" cue without claiming a specific
 * page as active. */
export function isCollectionScopedView(view: View): boolean {
  return COLLECTION_SCOPED_VIEW_NAMES.has(view.name);
}
