// ====== Code Summary ======
// A popover checklist toggling which columns render, grouped into labelled sections (Document,
// then metadata by origin: system / generated / upload) — TanStack's own column-visibility state,
// so hiding a column (including a metadata one) is free once its column def carries a `group`.

import type { Column, Table } from "@tanstack/react-table";
import { useEffect, useRef, useState } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { Button } from "../../components/Button";
import { theme } from "../../theme";
import { ColumnVisibilityGroup } from "./ColumnVisibilityGroup";
import { COLUMN_GROUP_LABELS, COLUMN_GROUP_ORDER } from "./columns/columnGroups";
import type { ColumnGroup } from "./types";

type GridColumn = Column<DocumentGridRow, unknown>;

function groupColumns(columns: GridColumn[]): Partial<Record<ColumnGroup, GridColumn[]>> {
  const grouped: Partial<Record<ColumnGroup, GridColumn[]>> = {};
  for (const column of columns) {
    const group = column.columnDef.meta?.group ?? "document";
    (grouped[group] ??= []).push(column);
  }
  return grouped;
}

export function ColumnVisibilityMenu({ table }: { table: Table<DocumentGridRow> }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    return () => document.removeEventListener("mousedown", onClickAway);
  }, [open]);

  const columns = table.getAllLeafColumns().filter((c) => c.id !== "__select" && c.id !== "__actions");
  const grouped = groupColumns(columns);
  const visibleGroups = COLUMN_GROUP_ORDER.filter((group) => (grouped[group]?.length ?? 0) > 0);

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <Button size="sm" onClick={() => setOpen((v) => !v)}>Columns</Button>
      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 30, minWidth: 240, maxHeight: 420,
            overflowY: "auto", background: theme.color.panel, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.m, boxShadow: theme.shadow.pop, padding: theme.space.s,
          }}
        >
          {visibleGroups.map((group, index) => (
            <ColumnVisibilityGroup
              key={group}
              label={COLUMN_GROUP_LABELS[group]}
              columns={grouped[group]!}
              divider={index > 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}
