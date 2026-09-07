// ====== Code Summary ======
// Compact 2-icon view switcher (grid on the LEFT, list on the RIGHT), file-explorer style — shared
// by the Workers and Collections pages. Click grid to switch to a card grid at the current column
// count; click list for one item per row. The active icon carries the forge accent, the other stays
// steel/muted (brand.md — accent marks the one thing that's "on").
//
// Long-press (~450ms) the grid button to open a small popover picking the column count (Auto/2/3/4).
// A hold alone would be mouse-only and undiscoverable, so the SAME button also opens that popover via
// right-click (`contextmenu`, no hold needed) and via the keyboard — `ArrowDown` or `Alt` while the
// grid button is focused — giving every input modality a no-hold path to the column picker.

import { useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";
import { theme as t } from "../../theme";
import { ColumnsMenu } from "./ColumnsMenu";
import type { ViewMode, ViewModeColumns } from "./useViewMode";

const LONG_PRESS_MS = 450;

function GridGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  );
}

function ListGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <rect x="1" y="2" width="14" height="3" rx="1" />
      <rect x="1" y="6.5" width="14" height="3" rx="1" />
      <rect x="1" y="11" width="14" height="3" rx="1" />
    </svg>
  );
}

function iconButtonStyle(active: boolean) {
  return {
    cursor: "pointer", width: 30, height: 26, display: "grid", placeItems: "center",
    borderRadius: t.radius.s, border: "none",
    background: active ? t.color.accentSoft : "transparent",
    color: active ? t.color.accentSafe : t.color.mute,
  } as const;
}

interface ViewModeToggleProps {
  mode: ViewMode;
  onChange: (mode: ViewMode) => void;
  /** Names what this toggle controls, e.g. "Workers" / "Collections" — feeds every aria-label. */
  label: string;
}

export function ViewModeToggle({ mode, onChange, label }: ViewModeToggleProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pressTimer = useRef<number | null>(null);
  const longPressed = useRef(false);
  // Remembers the last chosen column count so a plain click back to grid (from list) restores it
  // instead of resetting to "auto" — kept in sync whenever the controlled mode is grid.
  const lastColumnsRef = useRef<ViewModeColumns>(mode.kind === "grid" ? mode.columns : "auto");
  if (mode.kind === "grid") lastColumnsRef.current = mode.columns;

  const clearPressTimer = () => {
    if (pressTimer.current !== null) {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
  };

  const openColumnsMenu = () => {
    clearPressTimer();
    setMenuOpen(true);
  };

  const handleGridPointerDown = (e: PointerEvent<HTMLButtonElement>) => {
    // Only the secondary (right) button is excluded — it already opens the popover instantly via
    // `onContextMenu` below, so it must not ALSO arm the long-press timer. Left click, pen, and
    // touch primary contact all report `button` inconsistently across engines (real browsers use 0,
    // but touch's primary contact spec-reports -1, and it comes through as `undefined` in this
    // jsdom/testing-library harness) — gating on `=== 0` silently broke long-press for every input
    // that wasn't a real mouse left-click.
    if (e.button === 2) return;
    longPressed.current = false;
    pressTimer.current = window.setTimeout(() => {
      longPressed.current = true;
      openColumnsMenu();
    }, LONG_PRESS_MS);
  };

  const handleGridClick = () => {
    clearPressTimer();
    if (longPressed.current) {
      // The hold already opened the popover — the trailing click it produces must not also flip
      // the mode back to "grid" a second time (a no-op, but it would collapse the just-opened menu).
      longPressed.current = false;
      return;
    }
    onChange({ kind: "grid", columns: lastColumnsRef.current });
  };

  const handleGridContextMenu = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    openColumnsMenu();
  };

  const handleGridKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.altKey) {
      e.preventDefault();
      openColumnsMenu();
    }
  };

  const gridActive = mode.kind === "grid";

  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <div
        style={{
          display: "inline-flex", gap: 2, padding: 2, flexShrink: 0,
          background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m,
        }}
      >
        <button
          type="button"
          aria-pressed={gridActive}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={`${label} grid view — hold, right-click, or press Alt/ArrowDown for columns per row`}
          onPointerDown={handleGridPointerDown}
          onPointerUp={clearPressTimer}
          onPointerLeave={clearPressTimer}
          onClick={handleGridClick}
          onContextMenu={handleGridContextMenu}
          onKeyDown={handleGridKeyDown}
          style={iconButtonStyle(gridActive)}
        >
          <GridGlyph />
        </button>
        <button
          type="button"
          aria-pressed={!gridActive}
          aria-label={`${label} list view`}
          onClick={() => onChange({ kind: "list" })}
          style={iconButtonStyle(!gridActive)}
        >
          <ListGlyph />
        </button>
      </div>
      {menuOpen && (
        <ColumnsMenu
          selected={lastColumnsRef.current}
          onSelect={(columns) => onChange({ kind: "grid", columns })}
          onClose={() => setMenuOpen(false)}
        />
      )}
    </div>
  );
}
