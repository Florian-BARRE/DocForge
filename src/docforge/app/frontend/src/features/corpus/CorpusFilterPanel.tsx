// ====== Code Summary ======
// The corpus grid's collapsible per-column filter panel (toggled by FilterToggleButton) — one
// labeled control per filterable VISIBLE column (hiding a column via "Columns" hides its filter
// too), each sized to what its own control actually needs rather than squeezed into the data
// column's resizable grid width — the old per-column filter <tr> did the latter, which is exactly
// what truncated the number-range "min"/"max" placeholders to "mi"/"ma" on a narrow column.

import type { Table } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../api/corpus";
import { Button } from "../../components/Button";
import { theme } from "../../theme";
import { ColumnFilterCell } from "./ColumnFilterCell";
import { COLUMN_GROUP_ORDER, GROUP_HEADER_INFO, groupColumnsByOrigin } from "./columns/columnGroups";
import { FilterLegend } from "./FilterLegend";
import { type ColumnFilterKind, type ColumnFilterValue, type ColumnFiltersState } from "./types";

interface CorpusFilterPanelProps {
  table: Table<DocumentGridRow>;
  columnFilters: ColumnFiltersState;
  onColumnFilterChange: (columnId: string, value: ColumnFilterValue) => void;
  onClearAll: () => void;
}

// A content-appropriate width per control shape — a free-flowing flex-wrap row, not one shared
// narrow column. `bool` renders its own SegmentedControl (three buttons + a legend), so it needs
// the most room; `dateRange` stacks its two inputs vertically, so it needs the least.
const FILTER_WIDTH: Record<ColumnFilterKind, number> = {
  text: 200,
  enumMulti: 180,
  listIn: 220,
  bool: 260,
  numberRange: 170,
  dateRange: 150,
};

export function CorpusFilterPanel({ table, columnFilters, onColumnFilterChange, onClearAll }: CorpusFilterPanelProps) {
  const filterableColumns = table.getVisibleLeafColumns().filter((column) => column.columnDef.meta?.filterKind);
  if (filterableColumns.length === 0) return null;

  const grouped = groupColumnsByOrigin(filterableColumns);
  const sections = COLUMN_GROUP_ORDER.filter((group) => (grouped[group]?.length ?? 0) > 0);

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.m,
        padding: theme.space.m, background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l,
      }}
    >
      <FilterLegend />
      {sections.map((group, index) => (
        <div
          key={group}
          style={{
            borderTop: index > 0 ? `1px solid ${theme.color.line}` : "none",
            paddingTop: index > 0 ? theme.space.s : 0,
          }}
        >
          <span
            style={{
              display: "block", marginBottom: theme.space.xs, fontSize: theme.font.size.xs,
              fontWeight: theme.font.weight.semibold, textTransform: "uppercase", letterSpacing: "0.04em",
              color: theme.color.dim,
            }}
          >
            {GROUP_HEADER_INFO[group].label}
          </span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m, alignItems: "flex-end" }}>
            {grouped[group]!.map((column) => {
              const filterKind = column.columnDef.meta!.filterKind!;
              const label = typeof column.columnDef.header === "string" ? column.columnDef.header : column.id;
              return (
                <div key={column.id} style={{ width: FILTER_WIDTH[filterKind], flex: "none" }}>
                  {/* `bool` renders its own legend via SegmentedControl — a second label here
                     would be a redundant, worse-spaced repeat of the same text. */}
                  {filterKind !== "bool" && (
                    <span
                      style={{
                        display: "block", marginBottom: 4, fontSize: theme.font.size.xs,
                        fontWeight: theme.font.weight.semibold, color: theme.color.dim,
                      }}
                    >
                      {label}
                    </span>
                  )}
                  <ColumnFilterCell
                    columnId={column.id}
                    filterKind={filterKind}
                    label={label}
                    enumOptions={column.columnDef.meta?.enumOptions}
                    value={columnFilters[column.id]}
                    onChange={onColumnFilterChange}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}
      <div>
        <Button size="sm" variant="ghost" disabled={Object.keys(columnFilters).length === 0} onClick={onClearAll}>
          Clear filters
        </Button>
      </div>
    </div>
  );
}
