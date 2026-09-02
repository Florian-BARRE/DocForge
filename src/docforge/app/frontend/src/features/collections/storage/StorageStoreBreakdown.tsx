// ====== Code Summary ======
// One store's card — a neutral card (the store's colour lives ONLY in the header swatch dot, never
// on the card border, so it can't be misread as a status frame per brand.md's "reserve the colour"
// principle) with a header (swatch, label, total, share of the grand total, "≈ estimated" badge when
// the backend flags it) plus a collapsed-by-default disclosure of that store's per-field byte rows.
// The card never decides what "estimated" means; it only renders the flag it's handed.

import { AdvancedDisclosure } from "../../search-pipeline/AdvancedDisclosure";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { EstimatedBadge } from "./EstimatedBadge";
import { StorageMetricRow } from "./StorageMetricRow";

interface StorageStoreBreakdownProps {
  label: string;
  swatchColor: string;
  totalBytes: number;
  sharePercent: number;
  estimated: boolean;
  rows: { label: string; value: string }[];
  note?: string;
}

export function StorageStoreBreakdown({ label, swatchColor, totalBytes, sharePercent, estimated, rows, note }: StorageStoreBreakdownProps) {
  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, padding: t.space.l, boxShadow: t.shadow.sm, display: "flex", flexDirection: "column", gap: t.space.m }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.s }}>
        <span style={{ width: 9, height: 9, borderRadius: t.radius.pill, background: swatchColor, flexShrink: 0 }} />
        <span style={{ fontFamily: t.font.display, fontWeight: t.font.weight.semibold, fontSize: t.font.size.l, color: t.color.text }}>{label}</span>
        <span style={{ marginLeft: "auto", display: "flex", alignItems: "baseline", gap: t.space.xs }}>
          <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.l, color: t.color.text }}>{formatBytes(totalBytes)}</span>
          <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute }}>{sharePercent}%</span>
        </span>
        {estimated && <EstimatedBadge />}
      </div>

      {note && <div style={{ color: t.color.mute, fontSize: t.font.size.xs }}>{note}</div>}

      <AdvancedDisclosure summary="Breakdown">
        {rows.map((row) => <StorageMetricRow key={row.label} label={row.label} value={row.value} />)}
      </AdvancedDisclosure>
    </div>
  );
}
