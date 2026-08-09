// ====== Code Summary ======
// A stacked segmented bar — one segment per store, width proportional to that store's share of the
// grand total — plus a legend naming each store's total. Purely steel/muted chrome tones: forge
// orange stays reserved for the single active/primary thing elsewhere in the app (brand.md).

import type { CollectionStorage } from "../../../api/collections";
import { theme as t } from "../../../theme";
import { formatBytes } from "../../explorer/format";
import { STORAGE_STORES, storeStats } from "./storageStores";

interface StorageBarProps {
  storage: CollectionStorage;
}

export function StorageBar({ storage }: StorageBarProps) {
  const grandTotal = storage.grand_total_bytes;

  return (
    <div>
      <div style={{ display: "flex", height: 12, borderRadius: t.radius.pill, overflow: "hidden", background: t.color.surface2, border: `1px solid ${t.color.line}` }}>
        {grandTotal === 0 ? null : STORAGE_STORES.map(({ key, label, color }) => {
          const { totalBytes } = storeStats(storage, key);
          if (totalBytes === 0) return null;
          const widthPercent = (totalBytes / grandTotal) * 100;
          return <span key={key} title={`${label} — ${formatBytes(totalBytes)}`} style={{ width: `${widthPercent}%`, background: color }} />;
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
              {estimated && <span style={{ color: t.color.mute, fontSize: t.font.size.xs }}>≈</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
