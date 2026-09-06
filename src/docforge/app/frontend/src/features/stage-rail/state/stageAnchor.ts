// ====== Code Summary ======
// The single naming convention for a stage card's scroll anchor — shared by the card itself (the
// DOM id it carries) and anything that needs to jump-scroll or observe it (the minimap, the
// active-stage tracker), so the two never drift apart.

/** The DOM id a stage card's root element carries, keyed by its stable `StageView.key`. */
export function stageAnchorId(stageKey: string): string {
  return `stage-rail-anchor-${stageKey}`;
}
