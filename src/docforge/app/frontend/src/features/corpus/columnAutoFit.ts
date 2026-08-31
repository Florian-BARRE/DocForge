// ====== Code Summary ======
// Measures the widest rendered cell (header included) for one column and returns a fitted pixel
// width. Reads directly off the live DOM rather than the row data model, so it naturally accounts
// for whatever a cell actually renders (a chip's label, a formatted number, a truncated title) —
// and, since the grid is virtualized, it only ever sees the rows currently mounted, which matches
// "fit what's on screen" rather than paying to walk the full page's data.

import { theme } from "../../theme";

const MEASURE_FONT = `${theme.font.weight.medium} ${theme.font.size.s}px ${theme.font.family}`;
// Room for the cell's own horizontal padding plus a little slack so text doesn't sit flush
// against the resize handle.
const FIT_PADDING = 28;
const MAX_AUTO_FIT_WIDTH = 480;

let measureContext: CanvasRenderingContext2D | null = null;

function getMeasureContext(): CanvasRenderingContext2D | null {
  if (measureContext) return measureContext;
  const canvas = document.createElement("canvas");
  measureContext = canvas.getContext("2d");
  return measureContext;
}

/**
 * Computes an auto-fit width for a column from its currently rendered cells.
 *
 * @param tableRoot - The scrollable element containing the table (only its mounted rows are
 *   measured, matching what the user can actually see).
 * @param columnId - The TanStack column id to measure (cells carry it as `data-col-id`).
 * @param minSize - The column's configured floor, never undercut.
 * @returns The fitted width in pixels, clamped to `[minSize, MAX_AUTO_FIT_WIDTH]`.
 */
export function autoFitColumnWidth(tableRoot: HTMLElement, columnId: string, minSize: number): number {
  const ctx = getMeasureContext();
  if (ctx) ctx.font = MEASURE_FONT;
  const cells = tableRoot.querySelectorAll<HTMLElement>(`[data-col-id="${columnId}"]`);

  let widest = 0;
  cells.forEach((cell) => {
    const text = cell.textContent?.trim() ?? "";
    if (!text) return;
    const width = ctx ? ctx.measureText(text).width : text.length * (theme.font.size.s * 0.6);
    widest = Math.max(widest, width);
  });

  const fitted = Math.ceil(widest) + FIT_PADDING;
  return Math.min(MAX_AUTO_FIT_WIDTH, Math.max(minSize, fitted));
}
