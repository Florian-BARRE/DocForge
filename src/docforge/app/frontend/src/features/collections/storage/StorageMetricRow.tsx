// ====== Code Summary ======
// One label/value line inside a store's sub-breakdown — the value is a pre-formatted machine
// figure (byte size or count), always rendered in JetBrains Mono per brand.md.

import { theme as t } from "../../../theme";

interface StorageMetricRowProps {
  label: string;
  value: string;
}

export function StorageMetricRow({ label, value }: StorageMetricRowProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: t.space.m, padding: `${t.space.xs}px 0` }}>
      <span style={{ color: t.color.dim, fontSize: t.font.size.s }}>{label}</span>
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.text }}>{value}</span>
    </div>
  );
}
