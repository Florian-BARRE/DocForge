// ====== Code Summary ======
// All state behind the corpus grid page — the collection (field schema for metadata columns +
// format options), per-column filters, the single active sort, offset pagination, column
// visibility, the cross-page selection model — wired into the headless TanStack table. Extracted
// from `CorpusPage` so that component only renders; derivations live in corpusPageModel.ts.

import { getCoreRowModel, useReactTable, type SortingState, type VisibilityState } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import type { DocumentGridRow } from "../../api/corpus";
import { deleteDocument } from "../../api/explorer";
import type { Navigate } from "../../shell/view";
import { buildColumns } from "./columns/buildColumns";
import { DEFAULT_LIMIT, isFirstRunEmptyOf, showSelectAllPromptOf, sortOf } from "./corpusPageModel";
import { buildDocumentFilter } from "./filterBuilder";
import { countActiveFilters, type ColumnFiltersState, type ColumnFilterValue } from "./types";
import { useColumnLayout } from "./useColumnLayout";
import { useCorpusQuery } from "./useCorpusQuery";
import { useSelection } from "./useSelection";

export function useCorpusPage(collectionId: string, onNavigate: Navigate) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [collectionError, setCollectionError] = useState<string | null>(null);

  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  // "Chunks" is an engineering-facing pipeline internal — Pages/Size lead the default grid for a
  // business reader; Chunks stays one click away via the Columns menu, never removed.
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({ chunk_count: false });
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [offset, setOffset] = useState(0);

  const selection = useSelection();

  useEffect(() => {
    setCollectionError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setCollectionError(e instanceof Error ? e.message : String(e)));
  }, [collectionId]);

  const filter = useMemo(() => buildDocumentFilter(columnFilters), [columnFilters]);
  const sort = useMemo(() => sortOf(sorting), [sorting]);

  // A filter/collection change invalidates both the current page window and any in-flight
  // selection (a filter-mode selector is only meaningful against the filter it was captured with).
  // Sort does NOT reset either — re-sorting the same result set stays on the same page/selection.
  useEffect(() => {
    setOffset(0);
    selection.clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId, JSON.stringify(filter)]);

  const query = useCorpusQuery({ collectionId, filter, sort, limit, offset });

  const onOpen = (documentId: string) => onNavigate({ name: "document", collectionId, documentId });

  const onEnabledChanged = (documentId: string, enabled: boolean) => query.patchRow(documentId, { enabled });

  const onDelete = async (documentId: string) => {
    await deleteDocument(documentId);
    // Only "ids" mode needs a local update here — deleting a row already shrinks `query.total` on
    // refetch, so also adding it to "filtered" mode's `excludeIds` would double-subtract the same
    // removed document from `selection.count`.
    if (selection.mode === "ids" && selection.isSelected(documentId)) selection.toggleRow(documentId);
    query.refetch();
  };

  const columns = useMemo(
    () => buildColumns({
      selection,
      fields: collection?.fields ?? [],
      supportedFormats: collection?.supported_formats ?? [],
      onOpen,
      onEnabledChanged,
      onDelete,
      onReingested: query.refetch,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selection, collection?.fields, collection?.supported_formats, query.refetch],
  );

  const columnIds = useMemo(() => columns.map((c) => c.id).filter((id): id is string => !!id), [columns]);
  const columnLayout = useColumnLayout(collectionId, columnIds);

  const table = useReactTable<DocumentGridRow>({
    data: query.rows,
    columns,
    state: { sorting, columnVisibility, columnOrder: columnLayout.columnOrder, columnSizing: columnLayout.columnSizing },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnOrderChange: columnLayout.onColumnOrderChange,
    onColumnSizingChange: columnLayout.onColumnSizingChange,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.id,
    manualSorting: true,
    manualPagination: true,
    enableMultiSort: false,
    enableColumnResizing: true,
    columnResizeMode: "onChange",
    defaultColumn: { size: 150, minSize: 60, maxSize: 640 },
  });

  const onColumnFilterChange = (columnId: string, value: ColumnFilterValue) =>
    setColumnFilters((prev) => ({ ...prev, [columnId]: value }));

  const pageIds = query.rows.map((row) => row.id);
  const allOnPageSelected = selection.allOnPageSelected(pageIds);
  const hasActiveFilters = Object.keys(filter).length > 0;

  const bulkDone = () => {
    selection.clear();
    setOffset(0);
    query.refetch();
  };

  return {
    collection, collectionError, clearCollectionError: () => setCollectionError(null),
    columnFilters, onColumnFilterChange, clearColumnFilters: () => setColumnFilters({}),
    filtersOpen, toggleFilters: () => setFiltersOpen((v) => !v),
    activeFilterCount: countActiveFilters(columnFilters),
    filter, limit, offset, setOffset,
    changeLimit: (next: number) => { setLimit(next); setOffset(0); },
    selection, query, table, columnLayout, bulkDone,
    pageSize: pageIds.length,
    inFilteredMode: selection.mode === "filtered",
    showSelectAllPrompt: showSelectAllPromptOf(selection.mode, allOnPageSelected, query.total, pageIds.length),
    isFirstRunEmpty: isFirstRunEmptyOf(query, hasActiveFilters),
  };
}
