// ====== Code Summary ======
// The grid's cross-page selection model — either an explicit id set ("ids" mode, the rows the
// user hand-ticked) or "everything matching the current filter minus a few deselected ids"
// ("filtered" mode, the Gmail-style "select all N" escape hatch that avoids enumerating 100k
// ids). `toSelector` turns whichever mode is active into the exact `DocumentSelector` body the
// bulk-op endpoints expect.

import { useCallback, useState } from "react";
import type { DocumentFilter, DocumentSelector } from "../../api/corpus";

export type SelectionMode = "ids" | "filtered";

interface SelectionState {
  mode: SelectionMode;
  ids: Set<string>;
  excludeIds: Set<string>;
}

const EMPTY_SELECTION: SelectionState = { mode: "ids", ids: new Set(), excludeIds: new Set() };

export interface UseSelectionResult {
  mode: SelectionMode;
  isEmpty: boolean;
  isSelected: (id: string) => boolean;
  toggleRow: (id: string) => void;
  toggleAllOnPage: (pageIds: string[]) => void;
  allOnPageSelected: (pageIds: string[]) => boolean;
  selectAllFiltered: () => void;
  clear: () => void;
  count: (total: number) => number;
  toSelector: (filter: DocumentFilter) => DocumentSelector;
}

export function useSelection(): UseSelectionResult {
  const [state, setState] = useState<SelectionState>(EMPTY_SELECTION);

  const isSelected = useCallback(
    (id: string) => (state.mode === "ids" ? state.ids.has(id) : !state.excludeIds.has(id)),
    [state],
  );

  const toggleRow = useCallback((id: string) => {
    setState((prev) => {
      if (prev.mode === "ids") {
        const ids = new Set(prev.ids);
        if (ids.has(id)) ids.delete(id); else ids.add(id);
        return { ...prev, ids };
      }
      const excludeIds = new Set(prev.excludeIds);
      if (excludeIds.has(id)) excludeIds.delete(id); else excludeIds.add(id);
      return { ...prev, excludeIds };
    });
  }, []);

  const allOnPageSelected = useCallback(
    (pageIds: string[]) => pageIds.length > 0 && pageIds.every((id) => isSelected(id)),
    [isSelected],
  );

  const toggleAllOnPage = useCallback((pageIds: string[]) => {
    setState((prev) => {
      const allSelected = pageIds.length > 0
        && pageIds.every((id) => (prev.mode === "ids" ? prev.ids.has(id) : !prev.excludeIds.has(id)));
      if (prev.mode === "ids") {
        const ids = new Set(prev.ids);
        pageIds.forEach((id) => (allSelected ? ids.delete(id) : ids.add(id)));
        return { ...prev, ids };
      }
      const excludeIds = new Set(prev.excludeIds);
      pageIds.forEach((id) => (allSelected ? excludeIds.add(id) : excludeIds.delete(id)));
      return { ...prev, excludeIds };
    });
  }, []);

  const selectAllFiltered = useCallback(() => setState({ mode: "filtered", ids: new Set(), excludeIds: new Set() }), []);
  const clear = useCallback(() => setState(EMPTY_SELECTION), []);

  const count = useCallback(
    (total: number) => (state.mode === "ids" ? state.ids.size : Math.max(0, total - state.excludeIds.size)),
    [state],
  );

  const toSelector = useCallback(
    (filter: DocumentFilter): DocumentSelector =>
      state.mode === "ids" ? { document_ids: [...state.ids] } : { filter, exclude_ids: [...state.excludeIds] },
    [state],
  );

  const isEmpty = state.mode === "ids" && state.ids.size === 0;

  return { mode: state.mode, isEmpty, isSelected, toggleRow, toggleAllOnPage, allOnPageSelected, selectAllFiltered, clear, count, toSelector };
}
