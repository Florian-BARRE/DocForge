// ====== Code Summary ======
// One labelled section of the column-visibility menu — a header (name + column count, dimmed once
// every column in the group is hidden) with a group-wide show/hide toggle, followed by the
// group's per-column checkboxes.

import type { Column } from "@tanstack/react-table";
import type { DocumentGridRow } from "../../api/corpus";
import { Button } from "../../components/Button";
import { theme } from "../../theme";

interface ColumnVisibilityGroupProps {
  label: string;
  columns: Column<DocumentGridRow, unknown>[];
  divider: boolean;
}

export function ColumnVisibilityGroup({ label, columns, divider }: ColumnVisibilityGroupProps) {
  const visibleCount = columns.filter((column) => column.getIsVisible()).length;
  const allVisible = visibleCount === columns.length;
  const allHidden = visibleCount === 0;

  return (
    <div
      style={{
        borderTop: divider ? `1px solid ${theme.color.line}` : "none",
        marginTop: divider ? theme.space.xs : 0,
        paddingTop: divider ? theme.space.xs : 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.s, padding: "4px 6px" }}>
        <span
          style={{
            fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold, textTransform: "uppercase",
            letterSpacing: "0.04em", color: allHidden ? theme.color.mute : theme.color.dim,
          }}
        >
          {label} ({columns.length})
        </span>
        <Button
          size="sm"
          variant="ghost"
          style={{ padding: "1px 6px", fontSize: theme.font.size.xs, fontWeight: theme.font.weight.medium }}
          onClick={() => columns.forEach((column) => column.toggleVisibility(!allVisible))}
        >
          {allVisible ? "Hide all" : "Show all"}
        </Button>
      </div>
      {columns.map((column) => (
        <label
          key={column.id}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px", fontSize: theme.font.size.s, color: theme.color.text, cursor: "pointer" }}
        >
          <input type="checkbox" checked={column.getIsVisible()} onChange={column.getToggleVisibilityHandler()} />
          {typeof column.columnDef.header === "string" ? column.columnDef.header : column.id}
        </label>
      ))}
    </div>
  );
}
