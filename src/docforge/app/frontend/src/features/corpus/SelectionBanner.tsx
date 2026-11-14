// ====== Code Summary ======
// The banner above the corpus grid that offers the Gmail-style "select all N matching documents"
// escape hatch (when the page is fully ticked) or confirms that every match is selected.

import { Button } from "../../components/Button";
import { theme } from "../../theme";

interface SelectionBannerProps {
  /** True once "all matching documents" (filtered mode) is selected. */
  inFilteredMode: boolean;
  total: number;
  pageSize: number;
  onClear: () => void;
  onSelectAllFiltered: () => void;
}

export function SelectionBanner({ inFilteredMode, total, pageSize, onClear, onSelectAllFiltered }: SelectionBannerProps) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.s,
        flexWrap: "wrap", padding: `${theme.space.s}px ${theme.space.m}px`,
        background: theme.color.surface2, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.m, fontSize: theme.font.size.s, color: theme.color.text,
      }}
    >
      {inFilteredMode ? (
        <>
          <span>All <strong>{total.toLocaleString()}</strong> matching documents are selected.</span>
          <Button size="sm" variant="ghost" onClick={onClear}>Clear selection</Button>
        </>
      ) : (
        <>
          <span>All <strong>{pageSize}</strong> on this page are selected.</span>
          <Button size="sm" onClick={onSelectAllFiltered}>
            Select all {total.toLocaleString()} matching documents
          </Button>
        </>
      )}
    </div>
  );
}
