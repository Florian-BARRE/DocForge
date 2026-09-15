// ====== Code Summary ======
// Builds the command palette's three result groups (Collections / Go to / Actions) and ranks them
// against the current query. Kept separate from the dialog component so the "what are the possible
// destinations" data model is testable without mounting any UI.

import type { Collection } from "../../api/collections";
import { collectionIdOf, COLLECTION_SIDEBAR_PAGES } from "../sidebar/collectionSidebarConfig";
import { SIDEBAR_PAGES } from "../sidebar/sidebarConfig";
import type { Navigate, View } from "../view";
import { fuzzyScore } from "./fuzzyMatch";

export type CommandGroupLabel = "Collections" | "Go to" | "Actions";

export interface CommandItem {
  id: string;
  group: CommandGroupLabel;
  label: string;
  /** Short prose annotation shown beside the label (e.g. tags, "this collection") — never a machine
   *  value, so it renders in the regular UI font, not mono (see docs/brand.md). */
  hint?: string;
  run: () => void;
}

/**
 * The flat deployment nav, plus — when the current view sits inside a specific collection — that
 * collection's own tabs, so switching tabs is one keystroke away without leaving the palette.
 */
export function buildGoToItems(view: View, onNavigate: Navigate): CommandItem[] {
  const deployment: CommandItem[] = SIDEBAR_PAGES.map((page) => ({
    id: `go-to-${page.key}`,
    group: "Go to",
    label: page.label,
    run: () => onNavigate(page.view),
  }));

  const collectionId = collectionIdOf(view);
  if (!collectionId) return deployment;

  const collectionTabs: CommandItem[] = COLLECTION_SIDEBAR_PAGES.map((page) => ({
    id: `go-to-collection-${page.key}`,
    group: "Go to",
    label: page.label,
    hint: "this collection",
    run: () => onNavigate(page.build(collectionId)),
  }));

  return [...collectionTabs, ...deployment];
}

/**
 * Core cross-app actions. "Upload" only appears while inside a specific collection — it targets
 * that collection's Documents tab, where the shell header's own UploadPanel already lives (see
 * CollectionShell.tsx), so no cross-feature dialog wiring is needed for this slice.
 */
export function buildActionItems(view: View, onNavigate: Navigate): CommandItem[] {
  const actions: CommandItem[] = [
    { id: "action-new-collection", group: "Actions", label: "New collection", run: () => onNavigate({ name: "new-collection" }) },
    { id: "action-import-collection", group: "Actions", label: "Import collection", run: () => onNavigate({ name: "import-collection" }) },
  ];

  const collectionId = collectionIdOf(view);
  if (collectionId) {
    actions.push({
      id: "action-upload",
      group: "Actions",
      label: "Upload to this collection",
      run: () => onNavigate({ name: "collection-documents", collectionId }),
    });
  }
  return actions;
}

/** One item per collection, fuzzy-matched on name and tags via `filterItems`. */
export function buildCollectionItems(collections: Collection[], onNavigate: Navigate): CommandItem[] {
  return collections.map((c) => ({
    id: `collection-${c.id}`,
    group: "Collections",
    label: c.name,
    hint: c.tags.length > 0 ? c.tags.join(", ") : undefined,
    run: () => onNavigate({ name: "collection", collectionId: c.id }),
  }));
}

/** Ranks `items` against `query` (label + hint as the match haystack); empty query is a no-op. */
export function filterItems(items: CommandItem[], query: string): CommandItem[] {
  if (!query.trim()) return items;
  return items
    .map((item) => ({ item, score: fuzzyScore(query, item.hint ? `${item.label} ${item.hint}` : item.label) }))
    .filter((scored): scored is { item: CommandItem; score: number } => scored.score !== null)
    .sort((a, b) => a.score - b.score)
    .map((scored) => scored.item);
}
