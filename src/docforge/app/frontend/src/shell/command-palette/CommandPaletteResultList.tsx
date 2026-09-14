// ====== Code Summary ======
// Renders the palette's grouped result rows. Pure presentation — all filtering/ranking lives in
// commandItems.ts, all keyboard/query state lives in CommandPaletteDialog.tsx. The "selected" row
// (driven by keyboard or mouse hover, see CommandPaletteDialog) gets the one forge-accent highlight
// on screen, matching the brand rule that orange marks the single active thing.

import { theme as t } from "../../theme";
import type { CommandGroupLabel, CommandItem } from "./commandItems";

export interface CommandPaletteGroup {
  label: CommandGroupLabel;
  items: CommandItem[];
  /** True while this group's data is still loading and has produced zero items yet — kept visible
   *  (rather than hidden) so the palette doesn't look broken while the collections fetch is in flight. */
  loading?: boolean;
}

interface CommandPaletteResultListProps {
  groups: CommandPaletteGroup[];
  selectedId: string | null;
  onHoverSelect: (id: string) => void;
  onActivate: (item: CommandItem) => void;
}

export function CommandPaletteResultList({ groups, selectedId, onHoverSelect, onActivate }: CommandPaletteResultListProps) {
  const visibleGroups = groups.filter((g) => g.items.length > 0 || g.loading);
  const hasAnyResult = visibleGroups.some((g) => g.items.length > 0);

  return (
    <div role="listbox" aria-label="Command palette results" style={{ maxHeight: 360, overflowY: "auto", padding: t.space.s }}>
      {!hasAnyResult && (
        <div style={{ padding: t.space.l, textAlign: "center", color: t.color.mute, fontSize: t.font.size.m }}>
          No matches.
        </div>
      )}
      {visibleGroups.map((group) => (
        <div key={group.label} style={{ marginBottom: t.space.xs }}>
          <div
            style={{
              padding: `${t.space.xs}px ${t.space.s}px`, fontSize: t.font.size.xs, fontWeight: t.font.weight.semibold,
              letterSpacing: "0.04em", textTransform: "uppercase", color: t.color.mute,
            }}
          >
            {group.label}
          </div>
          {group.items.length === 0 && group.loading && (
            <div style={{ padding: `${t.space.xs}px ${t.space.s}px`, fontSize: t.font.size.s, color: t.color.mute }}>
              Loading…
            </div>
          )}
          {group.items.map((item) => {
            const selected = item.id === selectedId;
            return (
              <div
                key={item.id}
                id={item.id}
                role="option"
                aria-selected={selected}
                onMouseEnter={() => onHoverSelect(item.id)}
                onClick={() => onActivate(item)}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: t.space.s,
                  padding: `${t.space.s}px ${t.space.s}px`, borderRadius: t.radius.m, cursor: "pointer",
                  background: selected ? t.color.accentSoft : "transparent",
                  color: selected ? t.color.accentSafe : t.color.text,
                }}
              >
                <span style={{ fontSize: t.font.size.m, fontWeight: t.font.weight.medium }}>{item.label}</span>
                {item.hint && (
                  <span style={{ fontSize: t.font.size.xs, color: selected ? t.color.accentSafe : t.color.mute }}>
                    {item.hint}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
