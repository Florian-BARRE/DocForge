// ====== Code Summary ======
// The corpus grid's top-level page — owns every piece of query/selection/view state and wires
// them into the headless TanStack table: the collection's field schema (for metadata columns +
// format options), per-column filters, the single active sort, offset pagination, column
// visibility, and the cross-page selection model. Replaces the old DocumentsPage.

import { getCoreRowModel, useReactTable, type SortingState, type VisibilityState } from "@tanstack/react-table";
import { useEffect, useMemo, useState } from "react";
import { getCollection, type Collection } from "../../api/collections";
import type { DocumentGridRow, DocumentSort } from "../../api/corpus";
import { deleteDocument } from "../../api/explorer";
import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { BulkActionBar } from "./BulkActionBar";
import { buildColumns } from "./columns/buildColumns";
import { ColumnVisibilityMenu } from "./ColumnVisibilityMenu";
import { CorpusEstimateAction } from "./CorpusEstimateAction";
import { CorpusTable } from "./CorpusTable";
import { buildDocumentFilter } from "./filterBuilder";
import { Pager } from "./Pager";
import { apiFieldName, type ColumnFiltersState, type ColumnFilterValue } from "./types";
import { useColumnLayout } from "./useColumnLayout";
import { useCorpusQuery } from "./useCorpusQuery";
import { useSelection } from "./useSelection";

interface CorpusPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

const DEFAULT_LIMIT = 100;

export function CorpusPage({ collectionId, onNavigate }: CorpusPageProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [collectionError, setCollectionError] = useState<string | null>(null);

  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>({});
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
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
  const sort: DocumentSort | null = useMemo(() => {
    const active = sorting[0];
    return active ? { field: apiFieldName(active.id), direction: active.desc ? "desc" : "asc" } : null;
  }, [sorting]);

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
  const inFilteredMode = selection.mode === "filtered";
  // The page is fully ticked but the corpus spills onto other pages — offer the whole-set escape hatch.
  const showSelectAllPrompt = selection.mode === "ids" && allOnPageSelected && query.total > pageIds.length;
  // No column filter is active AND the query still came back empty — this collection has never had
  // anything ingested (as opposed to a real filter just matching nothing). Distinct copy + an actual
  // upload affordance, same tone as the collection Overview's first-run hero.
  const hasActiveFilters = Object.keys(filter).length > 0;
  const isFirstRunEmpty = !query.loading && !query.error && query.total === 0 && !hasActiveFilters;

  const bulkDone = () => {
    selection.clear();
    setOffset(0);
    query.refetch();
  };

  if (collectionError) return <ErrorState message={collectionError} onRetry={() => setCollectionError(null)} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  return (
    <div className="df-rise" style={{ padding: theme.space.xl, height: "100%", display: "flex", flexDirection: "column", gap: theme.space.m, minHeight: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.m, flexWrap: "wrap" }}>
        <BulkActionBar
          collectionId={collectionId}
          count={selection.count(query.total)}
          buildSelector={() => selection.toSelector(filter)}
          onDone={bulkDone}
        />
        <span style={{ marginLeft: "auto" }} />
        <CorpusEstimateAction
          collectionId={collectionId}
          filter={filter}
          selector={selection.toSelector(filter)}
          selectedCount={selection.count(query.total)}
          totalCount={query.total}
        />
        <ColumnVisibilityMenu
          table={table}
          onResetLayout={() => {
            columnLayout.reset();
            table.resetColumnVisibility();
          }}
        />
      </div>

      {(showSelectAllPrompt || inFilteredMode) && (
        <div
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.s,
            flexWrap: "wrap", padding: `${theme.space.s}px ${theme.space.m}px`,
            background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.m, fontSize: theme.font.size.s, color: theme.color.text,
          }}
        >
          {inFilteredMode ? (
            <>
              <span>All <strong>{query.total.toLocaleString()}</strong> matching documents are selected.</span>
              <Button size="sm" variant="ghost" onClick={selection.clear}>Clear selection</Button>
            </>
          ) : (
            <>
              <span>All <strong>{pageIds.length}</strong> on this page are selected.</span>
              <Button size="sm" onClick={selection.selectAllFiltered}>
                Select all {query.total.toLocaleString()} matching documents
              </Button>
            </>
          )}
        </div>
      )}

      {query.error ? (
        <ErrorState message={query.error} onRetry={query.refetch} />
      ) : isFirstRunEmpty ? (
        <EmptyState
          icon="↑"
          title="No documents yet"
          subtitle="Upload one to populate this collection's corpus — the Overview tab has the upload panel."
          action={
            <Button onClick={() => onNavigate({ name: "collection", collectionId })}>
              Upload a document
            </Button>
          }
        />
      ) : (
        <>
          <CorpusTable
            table={table}
            loading={query.loading}
            columnFilters={columnFilters}
            onColumnFilterChange={onColumnFilterChange}
          />
          <Pager total={query.total} limit={limit} offset={offset} onOffsetChange={setOffset} onLimitChange={(next) => { setLimit(next); setOffset(0); }} />
        </>
      )}
    </div>
  );
}
