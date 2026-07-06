// ====== Code Summary ======
// A small horizontal tab strip — the shared underline-tab look for any page that splits its
// content into named sections (currently the document explorer's Overview/Pages/IR/Chunks).

import { theme } from "../theme";

export interface TabItem<K extends string> {
  key: K;
  label: string;
}

interface TabNavProps<K extends string> {
  tabs: TabItem<K>[];
  active: K;
  onSelect: (key: K) => void;
}

export function TabNav<K extends string>({ tabs, active, onSelect }: TabNavProps<K>) {
  return (
    <div style={{ display: "flex", gap: theme.space.l, borderBottom: `1px solid ${theme.color.line}` }}>
      {tabs.map((tab) => {
        const isActive = tab.key === active;
        return (
          <button
            key={tab.key}
            onClick={() => onSelect(tab.key)}
            style={{
              background: "none", border: "none", cursor: "pointer",
              padding: `${theme.space.s}px 2px`, marginBottom: -1,
              color: isActive ? theme.color.accent : theme.color.dim,
              borderBottom: isActive ? `2px solid ${theme.color.accent}` : "2px solid transparent",
              fontSize: theme.font.size.m, fontWeight: isActive ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
