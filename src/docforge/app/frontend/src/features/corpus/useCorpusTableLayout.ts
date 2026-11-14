// ====== Code Summary ======
// State + gestures of the corpus grid shell: the scroll wrapper's measured width, the header
// drag-and-drop state, and the column handlers (reorder by drag / keyboard, auto-fit, keyboard
// resize). Extracted from CorpusTable so that component renders; the maths is in tableLayoutModel.ts.

import type { Table } from "@tanstack/react-table";
import { useEffect, useRef, useState, type DragEvent } from "react";
import type { DocumentGridRow } from "../../api/corpus";
import { autoFitColumnWidth } from "./columnAutoFit";
import { orderAfterDrop, orderAfterStep, type DragState } from "./tableLayoutModel";
import type { DropSide } from "./TableHeaderCell";

export function useCorpusTableLayout(table: Table<DocumentGridRow>) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  // Track the scroll wrapper's own width so a narrower column set (e.g. after hiding columns via
  // the "Columns" menu) can still stretch to fill it via `leftoverWidth`, instead of collapsing to
  // the MIN_TABLE_WIDTH floor and leaving dead space to its right.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => setContainerWidth(entries[0].contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const onHeaderDragStart = (columnId: string) => setDrag({ sourceId: columnId, overId: null, side: "after" });

  const onHeaderDragOver = (e: DragEvent<HTMLTableCellElement>, columnId: string) => {
    if (!drag || drag.sourceId === columnId) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const side: DropSide = e.clientX - rect.left < rect.width / 2 ? "before" : "after";
    setDrag((prev) => (prev ? { ...prev, overId: columnId, side } : prev));
  };

  const onHeaderDrop = () => {
    if (drag?.overId && drag.overId !== drag.sourceId) {
      table.setColumnOrder(orderAfterDrop(table.getState().columnOrder, drag.sourceId, drag.overId, drag.side));
    }
    setDrag(null);
  };

  const onAutoFit = (columnId: string) => {
    if (!scrollRef.current) return;
    const column = table.getColumn(columnId);
    if (!column) return;
    const minSize = column.columnDef.minSize ?? 60;
    const fitted = autoFitColumnWidth(scrollRef.current, columnId, minSize);
    table.setColumnSizing((prev) => ({ ...prev, [columnId]: fitted }));
  };

  // Keyboard counterpart to the mouse drag on ColumnResizeHandle — same `setColumnSizing` write.
  const onResizeStep = (columnId: string, nextSize: number) => {
    table.setColumnSizing((prev) => ({ ...prev, [columnId]: nextSize }));
  };

  // Keyboard counterpart to the mouse drag-and-drop reorder.
  const onReorderStep = (columnId: string, direction: -1 | 1) => {
    const next = orderAfterStep(table.getState().columnOrder, columnId, direction);
    if (next) table.setColumnOrder(next);
  };

  return {
    scrollRef, drag, containerWidth, endDrag: () => setDrag(null),
    onHeaderDragStart, onHeaderDragOver, onHeaderDrop, onAutoFit, onResizeStep, onReorderStep,
  };
}
