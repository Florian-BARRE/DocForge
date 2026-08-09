// ====== Code Summary ======
// A stacked segmented bar — one segment per store, width proportional to that store's share of the
// grand total, a hairline gap between segments and a min-width floor so a tiny slice never vanishes
// — plus a legend naming each store's total and share. Each store keeps its own warm data-viz hue
// (theme.color.store); forge orange stays reserved for the single active/primary thing (brand.md).

import { useState } from "react";
import type { CollectionStorage } from "../../../api/collections";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { STORAGE_STORES, storeSharePercent, storeStats } from "./storageStores";

interface StorageBarProps {
  storage: CollectionStorage;
}

const MIN_SEGMENT_PERCENT = 2.5;

export function StorageBar({ storage }: StorageBarProps) {
  const grandTotal = storage.grand_total_bytes;
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div>
      <div style={{ display: "flex", gap: 2, height: 14, background: t.color.surface2, borderRadius: t.radius.pill, border: `1px solid ${t.color.line}`, padding: 2 }}>
        {grandTotal === 0 ? null : STORAGE_STORES.map(({ key, label, color }) => {
          const { totalBytes } = storeStats(storage, key);
          if (totalBytes === 0) return null;
          const widthPercent = Math.max((totalBytes / grandTotal) * 100, MIN_SEGMENT_PERCENT);
          return (
            <span
              key={key}
              title={`${label} — ${formatBytes(totalBytes)} (${storeSharePercent(totalBytes, grandTotal)}%)`}
              onMouseEnter={() => setHovered(key)}
              onMouseLeave={() => setHovered((h) => (h === key ? null : h))}
              style={{
                width: `${widthPercent}%`,
                background: color,
                borderRadius: t.radius.pill,
                opacity: hovered === null || hovered === key ? 1 : 0.55,
                transition: "opacity .12s ease",
              }}
            />
          );
        })}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: t.space.l, marginTop: t.space.m }}>
        {STORAGE_STORES.map(({ key, label, color }) => {
          const { totalBytes, estimated } = storeStats(storage, key);
          return (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: t.space.xs }}>
              <span style={{ width: 9, height: 9, borderRadius: t.radius.pill, background: color, flexShrink: 0 }} />
              <span style={{ color: t.color.dim, fontSize: t.font.size.s }}>{label}</span>
              <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.text }}>{formatBytes(totalBytes)}</span>
              <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.xs, color: t.color.mute }}>{storeSharePercent(totalBytes, grandTotal)}%</span>
              {estimated && <span style={{ color: t.color.mute, fontSize: t.font.size.xs }}>≈</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
