// ====== Code Summary ======
// The cost-estimate panel's "Selected documents" scope — lets the user narrow the estimate to a
// corpus filter without leaving the Overview tab. A deliberate cross-feature import (not a
// duplicate): it drives the SAME filter controls and serializer the corpus grid uses
// (`ColumnFilterCell` + `buildDocumentFilter` + the `ColumnFiltersState` shape from
// `features/corpus/`), so the estimate's subset is byte-identical to what the grid itself would
// build — see CorpusEstimateDialog for the established precedent of this exact coupling running
// the other direction (corpus importing the collections/estimate result renderers). Unlike
// `CorpusFilterPanel`, this panel needs no `@tanstack/react-table` instance: `ColumnFilterCell`
// only needs a column id/kind/label, so a fixed catalogue-column list is enough — no grid to embed.

import { DOCUMENT_STATUSES } from "../../../api/explorer";
import { Button } from "../../../components/Button";
import { Chip } from "../../../components/Chip";
import { ColumnFilterCell } from "../../corpus/ColumnFilterCell";
import { countActiveFilters, type ColumnFilterKind, type ColumnFiltersState, type ColumnFilterValue } from "../../corpus/types";
import { theme } from "../../../theme";

interface FilterableField {
  id: string;
  label: string;
  filterKind: ColumnFilterKind;
  enumOptions?: string[];
}

// Mirrors the corpus grid's catalogue columns (`features/corpus/columns/baseColumns.tsx`) — every
// base column that carries a `filterKind` there, minus the grid-only display columns (chunk_count
// has none). `supportedFormats` is the one field-specific option, injected by the caller.
function filterableFields(supportedFormats: string[]): FilterableField[] {
  return [
    { id: "filename", label: "Filename", filterKind: "text" },
    { id: "title", label: "Title", filterKind: "text" },
    { id: "status", label: "Status", filterKind: "enumMulti", enumOptions: DOCUMENT_STATUSES },
    { id: "format", label: "Format", filterKind: "enumMulti", enumOptions: supportedFormats },
    { id: "language", label: "Language", filterKind: "listIn" },
    { id: "enabled", label: "Enabled", filterKind: "bool" },
    { id: "page_count", label: "Pages", filterKind: "numberRange" },
    { id: "file_size", label: "Size", filterKind: "numberRange" },
    { id: "created_at", label: "Created", filterKind: "dateRange" },
  ];
}

interface EstimateSubsetFilterPanelProps {
  columnFilters: ColumnFiltersState;
  onColumnFilterChange: (columnId: string, value: ColumnFilterValue) => void;
  onClearAll: () => void;
  supportedFormats: string[];
}

export function EstimateSubsetFilterPanel({ columnFilters, onColumnFilterChange, onClearAll, supportedFormats }: EstimateSubsetFilterPanelProps) {
  const activeCount = countActiveFilters(columnFilters);

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m, padding: theme.space.m,
        background: theme.color.surface2, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s }}>
        <span style={{ fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.dim, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Filter the documents to estimate
        </span>
        {activeCount > 0 && <Chip tone="accent">{activeCount}</Chip>}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m, alignItems: "flex-end" }}>
        {filterableFields(supportedFormats).map((field) => (
          <div key={field.id} style={{ width: field.filterKind === "bool" ? 260 : 190, flex: "none" }}>
            {field.filterKind !== "bool" && (
              <span style={{ display: "block", marginBottom: 4, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, color: theme.color.dim }}>
                {field.label}
              </span>
            )}
            <ColumnFilterCell
              columnId={field.id}
              filterKind={field.filterKind}
              label={field.label}
              enumOptions={field.enumOptions}
              value={columnFilters[field.id]}
              onChange={onColumnFilterChange}
            />
          </div>
        ))}
        <Button size="sm" variant="ghost" disabled={activeCount === 0} onClick={onClearAll}>
          Clear filters
        </Button>
      </div>
    </div>
  );
}
