// ====== Code Summary ======
// Pure breakpoint decision for the Layout tab's page/graph row. Side-by-side needs the page column
// PLUS the IR↔chunk graph's real minimum width (CONNECTOR + CHUNK_WIDTH + a margin, see
// IrChunkGraph.tsx) to both fit without squeezing the graph's fixed-width chunk column into an
// unreadable sliver and forcing it to scroll sideways — below this, the row stacks vertically
// instead (page render on top, full width; the graph below, also full width).

export const ROW_STACK_BREAKPOINT_PX = 1180;

/** `availableWidthPx <= 0` means "not measured yet" — side-by-side is the safe default then. */
export function shouldStackColumns(availableWidthPx: number): boolean {
  return availableWidthPx > 0 && availableWidthPx < ROW_STACK_BREAKPOINT_PX;
}
