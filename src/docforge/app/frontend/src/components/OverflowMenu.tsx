// ====== Code Summary ======
// Generic "more actions" affordance — a small kebab trigger that opens a click-away popover of
// menu items (see `OverflowMenuItem`). Shared by any list row or page header that needs to tuck a
// secondary/destructive action out of the primary button row (dashboard collection cards, the
// collection detail header). Purely chrome: it owns open/close + click-away/Escape, never the
// action itself — callers pass `OverflowMenuItem`s as children.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { theme as t } from "../theme";

/** A vertical three-dot kebab glyph, `currentColor`-only — brand.md bans emoji everywhere in the UI. */
function KebabGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="5" r="2" />
      <circle cx="12" cy="12" r="2" />
      <circle cx="12" cy="19" r="2" />
    </svg>
  );
}

interface OverflowMenuProps {
  /** Accessible name for the trigger button — should name what the menu acts on (e.g. the row's item). */
  label: string;
  /** Which side of the trigger the popover hangs from. */
  align?: "left" | "right";
  children: ReactNode;
}

export function OverflowMenu({ label, align = "right", children }: OverflowMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickAway);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div
      ref={rootRef}
      // The whole menu is chrome layered on top of whatever it sits in (a clickable dashboard card,
      // a page header) — never let a trigger or item click fall through to an ancestor's own onClick.
      onClick={(e) => e.stopPropagation()}
      style={{ position: "relative", display: "inline-flex" }}
    >
      <button
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        style={{
          width: 28, height: 28, display: "grid", placeItems: "center", flexShrink: 0,
          background: open ? t.color.surface2 : "transparent",
          color: t.color.dim,
          border: `1px solid ${open ? t.color.line : "transparent"}`,
          borderRadius: t.radius.m, cursor: "pointer",
        }}
      >
        <KebabGlyph />
      </button>
      {open && (
        <div
          role="menu"
          aria-label={label}
          onClick={() => setOpen(false)}
          style={{
            position: "absolute", top: "calc(100% + 4px)", zIndex: 30, minWidth: 190,
            ...(align === "right" ? { right: 0 } : { left: 0 }),
            background: t.color.panel, border: `1px solid ${t.color.line}`, borderRadius: t.radius.m,
            boxShadow: t.shadow.pop, padding: t.space.xs,
            display: "flex", flexDirection: "column", gap: 2,
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
