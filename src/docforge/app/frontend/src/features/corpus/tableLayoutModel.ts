// ====== Code Summary ======
// Pure maths of the corpus grid shell (CorpusTable / useCorpusTableLayout): the table's width, which
// column absorbs the leftover width, and the column-order edits for header drag-and-drop and the
// keyboard reorder. No React, no DOM.

import type { DropSide } from "./TableHeaderCell";
import { isPinnedColumn } from "./types";

export const ROW_HEIGHT = 40;
// `tableLayout: fixed` + an explicit table width needs a floor to compress against — without one
// the browser happily squeezes every column to near-zero at narrow viewports instead of ever
// overflowing the `overflow-x: auto` wrapper (scrollWidth stayed === clientWidth, so it never
// scrolled sideways). Shipped in 0.8.2 — keep honoring it against the live TanStack column sizes.
export const MIN_TABLE_WIDTH = 1100;

export interface DragState {
  sourceId: string;
  overId: string | null;
  side: DropSide;
}

/** The table's width: at least the floor, the container, and the sum of the column sizes. */
export function tableWidthOf(containerWidth: number, totalSize: number): number {
  return Math.max(MIN_TABLE_WIDTH, containerWidth, totalSize);
}

/**
 * Index of the last column that is not pinned (select / actions), or -1. `table-layout: fixed` with
 * an explicit `<table>` width wider than the sum of the `<colgroup>` widths hands the leftover space
 * to whichever <col> is LAST in the browser's own distribution — that's the non-resizable "__actions"
 * column, which renders as a wide blank void after its small button cluster (a "ghost" trailing
 * column). Routing the leftover to the last REAL column instead reads as one column stretching to
 * fill the row rather than empty dead space.
 */
export function lastFlexColumnIndexOf(columnIds: string[]): number {
  for (let i = columnIds.length - 1; i >= 0; i--) {
    if (!isPinnedColumn(columnIds[i])) return i;
  }
  return -1;
}

/** Column order after dropping the dragged column before/after the hovered one. */
export function orderAfterDrop(current: string[], sourceId: string, overId: string, side: DropSide): string[] {
  const without = current.filter((id) => id !== sourceId);
  const targetIndex = without.indexOf(overId);
  const insertAt = side === "before" ? targetIndex : targetIndex + 1;
  return [...without.slice(0, insertAt), sourceId, ...without.slice(insertAt)];
}

/**
 * Column order after the keyboard reorder: swaps with the adjacent reorderable column (pinned
 * select/actions columns sit at the array's edges and are skipped). Null when nothing moves.
 */
export function orderAfterStep(current: string[], columnId: string, direction: -1 | 1): string[] | null {
  const index = current.indexOf(columnId);
  if (index === -1) return null;
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= current.length || isPinnedColumn(current[targetIndex])) return null;
  const next = [...current];
  [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
  return next;
}
