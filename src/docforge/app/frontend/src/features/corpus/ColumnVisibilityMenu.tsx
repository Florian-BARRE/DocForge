// ====== Code Summary ======
// A popover checklist toggling which columns render — TanStack's own column-visibility state, so
// hiding a column (including a metadata one) is free once the column defs exist.

import type { Table } from "@tanstack/react-table";
import { useEffect, useRef, useState } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { Button } from "../../components/Button";
import { theme } from "../../theme";

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

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <Button size="sm" onClick={() => setOpen((v) => !v)}>Columns</Button>
      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 30, minWidth: 200, maxHeight: 340,
            overflowY: "auto", background: theme.color.panel, border: `1px solid ${theme.color.line}`,
            borderRadius: theme.radius.m, boxShadow: theme.shadow.pop, padding: theme.space.s,
          }}
        >
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
      )}
    </div>
  );
}
