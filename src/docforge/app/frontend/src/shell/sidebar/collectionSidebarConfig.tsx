// ====== Code Summary ======
// The COLLECTION-scope nav model — the flat page list the persistent rail swaps to while the current
// view sits inside a specific collection (Supabase-style scope swap: the same rail owns the in-
// collection nav instead of a redundant horizontal tab strip). Mirrors the deployment-scope
// `sidebarConfig.tsx`, but each page BUILDS its View from the current collectionId (the collection is
// only known at render time), and `activeCollectionKey` folds the entity views (a document → Documents,
// a job → Activity) back onto their owning page so the rail keeps a correct "where am I" highlight.

import type { ReactNode } from "react";
import type { View } from "../view";
import {
  ActivityGlyph, DocumentsGlyph, HomeGlyph, PipelinesGlyph, SchemaGlyph, SearchGlyph, SettingsGlyph,
} from "./icons";

export interface CollectionSidebarPage {
  key: string;
  label: string;
  icon: ReactNode;
  /** The collection is only known at render time, so each page builds its own target View. */
  build: (collectionId: string) => View;
  isActive: (view: View) => boolean;
}

export const COLLECTION_SIDEBAR_PAGES: CollectionSidebarPage[] = [
  {
    key: "overview", label: "Overview", icon: <HomeGlyph />,
    build: (id) => ({ name: "collection", collectionId: id }),
    isActive: (v) => v.name === "collection",
  },
  {
    key: "documents", label: "Documents", icon: <DocumentsGlyph />,
    build: (id) => ({ name: "collection-documents", collectionId: id }),
    // A single document's explorer is nested under Documents, so it keeps this page lit.
    isActive: (v) => v.name === "collection-documents" || v.name === "document",
  },
  {
    key: "search", label: "Search", icon: <SearchGlyph />,
    build: (id) => ({ name: "collection-search", collectionId: id }),
    isActive: (v) => v.name === "collection-search",
  },
  {
    key: "pipelines", label: "Pipelines", icon: <PipelinesGlyph />,
    build: (id) => ({ name: "collection-pipelines", collectionId: id }),
    isActive: (v) => v.name === "collection-pipelines",
  },
  {
    key: "schema", label: "Schema", icon: <SchemaGlyph />,
    build: (id) => ({ name: "collection-schema", collectionId: id }),
    isActive: (v) => v.name === "collection-schema",
  },
  {
    key: "activity", label: "Activity", icon: <ActivityGlyph />,
    build: (id) => ({ name: "collection-activity", collectionId: id }),
    // A single job's detail is reached from this collection's Activity, so it keeps it lit.
    isActive: (v) => v.name === "collection-activity" || v.name === "job",
  },
  {
    key: "settings", label: "Settings", icon: <SettingsGlyph />,
    build: (id) => ({ name: "collection-settings", collectionId: id }),
    isActive: (v) => v.name === "collection-settings",
  },
];

/** The active collection page's key, or null when the view isn't collection-scoped. */
export function activeCollectionKey(view: View): string | null {
  return COLLECTION_SIDEBAR_PAGES.find((page) => page.isActive(view))?.key ?? null;
}

/** The collection id a collection-scoped view carries, or null for deployment-scope views. */
export function collectionIdOf(view: View): string | null {
  switch (view.name) {
    case "collection":
    case "collection-documents":
    case "collection-search":
    case "collection-pipelines":
    case "collection-schema":
    case "collection-activity":
    case "collection-settings":
    case "document":
    case "job":
      return view.collectionId;
    default:
      return null;
  }
}
