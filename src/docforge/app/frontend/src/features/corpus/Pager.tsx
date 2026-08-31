// ====== Code Summary ======
// Offset pagination controls + the total match count — deep sets are handled by paging rather
// than trying to hold 100k rows in the DOM at once (each page's rows are still virtualized).

import { Button } from "../../components/Button";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";

interface PagerProps {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
  onLimitChange: (limit: number) => void;
}

const PAGE_SIZES = [50, 100, 200];

export function Pager({ total, limit, offset, onOffsetChange, onLimitChange }: PagerProps) {
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));

  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.m, fontSize: theme.font.size.s, color: theme.color.dim }}>
      <span>{total.toLocaleString()} document{total === 1 ? "" : "s"}</span>
      <span style={{ marginLeft: "auto" }} />
      <select
        value={limit}
        onChange={(e) => onLimitChange(Number(e.target.value))}
        style={{ ...inputStyle, width: "auto", padding: "4px 8px", fontSize: theme.font.size.s }}
      >
        {PAGE_SIZES.map((size) => <option key={size} value={size}>{size} / page</option>)}
      </select>
      <Button size="sm" disabled={offset === 0} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>Prev</Button>
      <span style={{ fontFamily: theme.font.mono }}>{page} / {pageCount}</span>
      <Button size="sm" disabled={offset + limit >= total} onClick={() => onOffsetChange(offset + limit)}>Next</Button>
    </div>
  );
}
