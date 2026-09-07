// ====== Code Summary ======
// The small popover opened from `ViewModeToggle`'s grid button — picks the fixed column count
// (Auto/2/3/4) for the grid layout. `role="menu"` of `menuitemradio` rows is the ARIA-sanctioned
// pattern for a popup single-select list opened from a button (Windows Explorer's own "view options"
// menu uses the same shape). Self-contained click-away + Escape close, mirroring `OverflowMenu`.

import { useEffect, useRef } from "react";
import { theme as t } from "../../theme";
import type { ViewModeColumns } from "./useViewMode";

const COLUMN_OPTIONS: { value: ViewModeColumns; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: 2, label: "2" },
  { value: 3, label: "3" },
  { value: 4, label: "4" },
];

interface ColumnsMenuProps {
  selected: ViewModeColumns;
  onSelect: (columns: ViewModeColumns) => void;
  onClose: () => void;
}

export function ColumnsMenu({ selected, onSelect, onClose }: ColumnsMenuProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClickAway = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) onClose();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onClickAway);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickAway);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose]);

  return (
    <div
      ref={rootRef}
      role="menu"
      aria-label="Columns per row"
      style={{
        position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 30, minWidth: 110,
        background: t.color.panel, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m,
        boxShadow: t.shadow.pop, padding: t.space.xs,
        display: "flex", flexDirection: "column", gap: 2,
      }}
    >
      {COLUMN_OPTIONS.map((opt) => {
        const active = opt.value === selected;
        return (
          <button
            key={opt.value}
            type="button"
            role="menuitemradio"
            aria-checked={active}
            onClick={() => { onSelect(opt.value); onClose(); }}
            style={{
              display: "flex", alignItems: "center", width: "100%", textAlign: "left",
              background: active ? t.color.accentSoft : "transparent",
              color: active ? t.color.accentSafe : t.color.text,
              border: "none", borderRadius: t.radius.s,
              padding: `${t.space.xs}px ${t.space.s}px`,
              fontFamily: typeof opt.value === "number" ? t.font.mono : t.font.family,
              fontSize: t.font.size.s, fontWeight: active ? t.font.weight.semibold : t.font.weight.normal,
              cursor: "pointer",
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
