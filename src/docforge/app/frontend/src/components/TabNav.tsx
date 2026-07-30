// ====== Code Summary ======
// A small horizontal tab strip — the shared underline-tab look for any page that splits its
// content into named sections (currently the document explorer's Overview/Pages/IR/Chunks).

import { useState } from "react";
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

function Tab({ label, isActive, onClick }: { label: string; isActive: boolean; onClick: () => void }) {
  const [hover, setHover] = useState(false);
  const color = isActive ? theme.color.accent : hover ? theme.color.text : theme.color.dim;
  return (
    <button
      onClick={onClick}
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

export function TabNav<K extends string>({ tabs, active, onSelect }: TabNavProps<K>) {
  return (
    <div style={{ display: "flex", gap: theme.space.l, borderBottom: `1px solid ${theme.color.line}` }}>
      {tabs.map((tab) => (
        <Tab key={tab.key} label={tab.label} isActive={tab.key === active} onClick={() => onSelect(tab.key)} />
      ))}
    </div>
  );
}
