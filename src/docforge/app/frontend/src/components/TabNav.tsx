// ====== Code Summary ======
// A small horizontal tab strip — the shared underline-tab look for any page that splits its
// content into named sections (the document explorer's Overview/Pages/IR/Chunks, the collection
// shell's sub-tabs) OR a segmented filter (Auth Keys' Active/Revoked/All — same look, different
// semantics: it filters one list rather than switching between panels, so it renders `role="group"`
// instead of `role="tablist"`, see the `role` prop). Wired as a real ARIA tablist by default:
// `role="tab"`, `aria-selected`, roving tabindex, Left/Right/Home/End move focus and activate.

import { useState } from "react";
import { theme } from "../theme";
import { useRovingTabIndex } from "./useRovingTabIndex";

export interface TabItem<K extends string> {
  key: K;
  label: string;
}

/** Deterministic id for a tab button — exported so a consumer can point its panel's `aria-labelledby` at it. */
export function tabButtonId(navId: string, key: string): string {
  return `${navId}-tab-${key}`;
}

interface TabNavProps<K extends string> {
  tabs: TabItem<K>[];
  active: K;
  onSelect: (key: K) => void;
  /** Stable id prefix for this tab strip — must be unique on the page (a page can host more than one). */
  navId: string;
  /** Accessible name for the strip itself (e.g. "Document sections", "Key status filter"). */
  ariaLabel: string;
  /** "tablist" (default) switches distinct content panels; "group" is a segmented filter/toggle. */
  role?: "tablist" | "group";
  /** id of the single panel this strip controls — only meaningful when `role="tablist"`. */
  panelId?: string;
}

interface TabProps<K extends string> {
  navId: string;
  itemKey: K;
  label: string;
  isActive: boolean;
  isGroup: boolean;
  panelId?: string;
  onClick: () => void;
  registerRef: (el: HTMLElement | null) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

function Tab<K extends string>({ navId, itemKey, label, isActive, isGroup, panelId, onClick, registerRef, onKeyDown }: TabProps<K>) {
  const [hover, setHover] = useState(false);
  // Text uses accentSafe (accent-strong on paper) — plain accent fails AA as text on paper. The
  // underline below is non-text (a 3:1 graphical-object minimum applies, which plain accent clears),
  // so it stays on the base accent — this is the one "deepest active level" the tab owns, not a
  // second stacked accent treatment.
  const color = isActive ? theme.color.accentSafe : hover ? theme.color.text : theme.color.dim;
  return (
    <button
      id={tabButtonId(navId, itemKey)}
      ref={registerRef}
      role={isGroup ? undefined : "tab"}
      aria-selected={isGroup ? undefined : isActive}
      aria-pressed={isGroup ? isActive : undefined}
      aria-controls={isGroup ? undefined : panelId}
      tabIndex={isActive ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: "none", border: "none", cursor: "pointer",
        padding: `${theme.space.s}px 2px`, marginBottom: -1, color,
        borderBottom: `2px solid ${isActive ? theme.color.accent : hover ? theme.color.line : "transparent"}`,
        fontSize: theme.font.size.m, fontWeight: isActive ? 600 : 400,
        transition: "color .15s ease, border-color .15s ease",
      }}
    >
      {label}
    </button>
  );
}

export function TabNav<K extends string>({ tabs, active, onSelect, navId, ariaLabel, role = "tablist", panelId }: TabNavProps<K>) {
  const order = tabs.map((tab) => tab.key);
  const roving = useRovingTabIndex(order, onSelect);

  return (
    <div role={role} aria-label={ariaLabel} style={{ display: "flex", gap: theme.space.l, borderBottom: `1px solid ${theme.color.line}` }}>
      {tabs.map((tab) => (
        <Tab
          key={tab.key}
          navId={navId}
          itemKey={tab.key}
          label={tab.label}
          isActive={tab.key === active}
          isGroup={role === "group"}
          panelId={panelId}
          onClick={() => onSelect(tab.key)}
          registerRef={roving.register(tab.key)}
          onKeyDown={(e) => roving.onKeyDown(e, tab.key)}
        />
      ))}
    </div>
  );
}
