// ====== Code Summary ======
// A stacked segmented bar — one segment per store, width proportional to that store's share of the
// grand total, a hairline gap between segments and a true PIXEL min-width floor (via CSS `minWidth`,
// not a percent floor) so a tiny slice stays visible no matter how narrow the bar's own flex-basis
// renders at — plus a legend naming each store's total and share. Each store keeps its own warm
// data-viz hue (theme.color.store); forge orange stays reserved for the single active/primary thing
// (brand.md).

import { useState } from "react";
import type { CollectionStorage } from "../../../api/collections";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { STORAGE_STORES, storeSharePercent, storeStats } from "./storageStores";

interface StorageBarProps {
  storage: CollectionStorage;
}

// A CSS floor, not a percent floor: `minWidth` wins over a computed `width` that resolves smaller
// than it, regardless of how wide the bar's own container happens to be — a percent-only floor
// (the previous approach) could still round away to sub-pixel on a narrow bar.
const SEGMENT_MIN_WIDTH_PX = 4;

export function StorageBar({ storage }: StorageBarProps) {
  const grandTotal = storage.grand_total_bytes;
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div>
      <div style={{ display: "flex", gap: 2, height: 14, background: t.color.surface2, borderRadius: t.radius.pill, border: `1px solid ${t.color.line}`, padding: 2 }}>
        {grandTotal === 0 ? null : STORAGE_STORES.map(({ key, label, color }) => {
          const { totalBytes } = storeStats(storage, key);
          if (totalBytes === 0) return null;
          const widthPercent = (totalBytes / grandTotal) * 100;
          return (
            <span
              key={key}
              title={`${label} — ${formatBytes(totalBytes)} (${storeSharePercent(totalBytes, grandTotal)}%)`}
              onMouseEnter={() => setHovered(key)}
              onMouseLeave={() => setHovered((h) => (h === key ? null : h))}
              style={{
                width: `${widthPercent}%`,
                minWidth: SEGMENT_MIN_WIDTH_PX,
                flexShrink: 0,
                // A hairline of the track's own background between segments, on top of the flex
                // `gap` above — belt-and-suspenders so two adjacent close-hued stores never visually
                // fuse into one slab.
                boxShadow: `inset 0 0 0 1px ${t.color.surface2}`,
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
              {estimated && totalBytes > 0 && <span style={{ color: t.color.mute, fontSize: t.font.size.xs }}>≈</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
