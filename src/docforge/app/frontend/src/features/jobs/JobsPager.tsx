// ====== Code Summary ======
// Offset pagination for AllJobsPage's fleet-wide job list — a small local twin of
// features/corpus/Pager.tsx (feature slices don't cross-import, see agent-memory/frontend/
// feature_slice_isolation.md), fixed to one page size rather than a selector since a jobs fleet
// list has no equivalent to the corpus grid's dense/sparse viewing modes.

import { Button } from "../../components/Button";
import { theme } from "../../theme";

interface JobsPagerProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}

export function JobsPager({ total, limit, offset, onOffsetChange }: JobsPagerProps) {
  if (total === 0) return null;
  const start = offset + 1;
  const end = Math.min(offset + limit, total);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.m, fontSize: theme.font.size.s, color: theme.color.dim }}>
      <span>{start}–{end} of {total.toLocaleString()}</span>
      <span style={{ marginLeft: "auto" }} />
      <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>
        Prev
      </Button>
      <Button size="sm" variant="ghost" disabled={end >= total} onClick={() => onOffsetChange(offset + limit)}>
        Next
      </Button>
    </div>
  );
}
