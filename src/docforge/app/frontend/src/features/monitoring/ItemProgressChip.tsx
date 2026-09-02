// ====== Code Summary ======
// Compact "done / total" indicator for the CURRENT fan-out stage (e.g. `per_figure` 12/40) —
// reused by JobRow and JobDetailPage. Renders nothing on a non-fan-out stage (caller guards that).

import { theme } from "../../theme";

interface ItemProgressChipProps {
  itemsDone: number;
  itemsTotal: number;
}

export function ItemProgressChip({ itemsDone, itemsTotal }: ItemProgressChipProps) {
  return (
    <span
      title={`${itemsDone} of ${itemsTotal} items processed in this stage`}
      style={{
        fontFamily: theme.font.mono, fontSize: theme.font.size.xs, fontWeight: theme.font.weight.semibold,
        color: theme.color.accentSafe, background: theme.color.accentSoft, border: `1px solid ${theme.color.accentLine}`,
        borderRadius: theme.radius.pill, padding: "1px 7px", whiteSpace: "nowrap",
      }}
    >
      {itemsDone} / {itemsTotal}
    </span>
  );
}
