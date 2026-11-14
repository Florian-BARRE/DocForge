// ====== Code Summary ======
// The corpus grid's top-level page — owns every piece of query/selection/view state and wires
// them into the headless TanStack table: the collection's field schema (for metadata columns +
// format options), per-column filters, the single active sort, offset pagination, column
// visibility, and the cross-page selection model. Replaces the old DocumentsPage.

import { Button } from "../../components/Button";
import { EmptyState } from "../../components/EmptyState";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";
import { BulkActionBar } from "./BulkActionBar";
import { ColumnVisibilityMenu } from "./ColumnVisibilityMenu";
import { CorpusEstimateAction } from "./CorpusEstimateAction";
import { CorpusFilterPanel } from "./CorpusFilterPanel";
import { CorpusTable } from "./CorpusTable";
import { FilterToggleButton } from "./FilterToggleButton";
import { Pager } from "./Pager";
import { SelectionBanner } from "./SelectionBanner";
import { useCorpusPage } from "./useCorpusPage";

interface CorpusPageProps {
  collectionId: string;
  onNavigate: Navigate;
}

export function CorpusPage({ collectionId, onNavigate }: CorpusPageProps) {
  const {
    collection, collectionError, clearCollectionError, columnFilters, onColumnFilterChange, clearColumnFilters,
    filtersOpen, toggleFilters, activeFilterCount, filter, limit, offset, setOffset, changeLimit,
    selection, query, table, columnLayout, bulkDone, pageSize, inFilteredMode, showSelectAllPrompt, isFirstRunEmpty,
  } = useCorpusPage(collectionId, onNavigate);

  if (collectionError) return <ErrorState message={collectionError} onRetry={() => clearCollectionError()} />;
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
        <FilterToggleButton
          open={filtersOpen}
          activeCount={activeFilterCount}
          onToggle={toggleFilters}
        />
        <ColumnVisibilityMenu
          table={table}
          onResetLayout={() => {
            columnLayout.reset();
            table.resetColumnVisibility();
          }}
        />
      </div>

      {filtersOpen && (
        <CorpusFilterPanel
          table={table}
          columnFilters={columnFilters}
          onColumnFilterChange={onColumnFilterChange}
          onClearAll={clearColumnFilters}
        />
      )}

      {(showSelectAllPrompt || inFilteredMode) && (
        <SelectionBanner
          inFilteredMode={inFilteredMode}
          total={query.total}
          pageSize={pageSize}
          onClear={selection.clear}
          onSelectAllFiltered={selection.selectAllFiltered}
        />
      )}

      {query.error ? (
        <ErrorState message={query.error} onRetry={query.refetch} />
      ) : isFirstRunEmpty ? (
        <EmptyState
          icon="↑"
          title="No documents yet"
          subtitle="Upload one to populate this collection's documents — the Overview tab has the upload panel."
          action={
            <Button onClick={() => onNavigate({ name: "collection", collectionId })}>
              Upload a document
            </Button>
          }
        />
      ) : (
        <>
          <CorpusTable table={table} loading={query.loading} />
          <Pager total={query.total} limit={limit} offset={offset} onOffsetChange={setOffset} onLimitChange={changeLimit} />
        </>
      )}
    </div>
  );
}
