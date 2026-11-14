// ====== Code Summary ======
// Pure derivations of the corpus page (CorpusPage / useCorpusPage): the API sort from the table's
// sorting state, and the selection-banner / first-run-empty flags. No React.

import type { SortingState } from "@tanstack/react-table";
import type { DocumentSort } from "../../api/corpus";
import { apiFieldName } from "./types";

export const DEFAULT_LIMIT = 100;

/** The single active table sort as the API's sort object (null when unsorted). */
export function sortOf(sorting: SortingState): DocumentSort | null {
  const active = sorting[0];
  return active ? { field: apiFieldName(active.id), direction: active.desc ? "desc" : "asc" } : null;
}

/** The page is fully ticked but the corpus spills onto other pages — offer the whole-set escape hatch. */
export function showSelectAllPromptOf(
  mode: "ids" | "filtered",
  allOnPageSelected: boolean,
  total: number,
  pageSize: number,
): boolean {
  return mode === "ids" && allOnPageSelected && total > pageSize;
}

/**
 * No column filter is active AND the query still came back empty — this collection has never had
 * anything ingested (as opposed to a real filter just matching nothing).
 */
export function isFirstRunEmptyOf(
  query: { loading: boolean; error: string | null; total: number },
  hasActiveFilters: boolean,
): boolean {
  return !query.loading && !query.error && query.total === 0 && !hasActiveFilters;
}
