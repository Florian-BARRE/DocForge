// ====== Code Summary ======
// One volume figure in the headline's mini-grid (pages, chunks, vectors, storage) — a small
// uppercase label over a mono machine value, matching StorageMetricRow's read language.

import { theme as t } from "../../../theme";

interface CostEstimateVolumeStatProps {
  label: string;
  value: string;
}

export function CostEstimateVolumeStat({ label, value }: CostEstimateVolumeStatProps) {
  return (
    <div>
      <div style={{ color: t.color.mute, fontSize: t.font.size.xs, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
      <div style={{ fontFamily: t.font.mono, fontSize: t.font.size.l, color: t.color.text, marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}
