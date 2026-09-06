// ====== Code Summary ======
// A single resource-usage bar (CPU % or memory %) shared by the worker resource readout. The fill
// is visually clamped at 100% — a multi-core worker's CPU can legitimately sample above 100% — but
// the label always shows the true, uncapped value so nothing is silently hidden. Forge orange marks
// "hot" (at/over `hotThreshold` of `max`); steel/muted at rest — brand.md reserves orange for the
// one active/at-capacity signal, never decoration.

import { theme } from "../../theme";

interface ResourceBarProps {
  label: string;
  /** Raw sampled value; may exceed `max` (e.g. CPU% on a multi-core host). Null = not reported by
   *  this worker (old heartbeat row, non-sampling build, or an unprimed first tick). */
  value: number | null;
  /** The bar's 100%-fill reference (100 for a percent metric). */
  max: number;
  /** Fraction of `max` (0-1) at/above which the bar reads as "hot" → forge accent. */
  hotThreshold?: number;
  /** Formats the raw value for display next to the label. */
  formatValue: (value: number) => string;
}

export function ResourceBar({ label, value, max, hotThreshold = 0.85, formatValue }: ResourceBarProps) {
  const hot = value !== null && value / max >= hotThreshold;
  const fillPercent = value === null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  const barColor = value === null ? theme.color.mute : hot ? theme.color.accent : theme.color.info;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: theme.font.size.xs, color: theme.color.dim }}>
        <span>{label}</span>
        <span
          style={{
            fontFamily: theme.font.mono,
            color: value === null ? theme.color.mute : hot ? theme.color.accent : theme.color.text,
            fontWeight: hot ? theme.font.weight.semibold : theme.font.weight.normal,
          }}
        >
          {value === null ? "not reported" : formatValue(value)}
        </span>
      </div>
      <div style={{ background: theme.color.surface2, borderRadius: theme.radius.pill, height: 6, overflow: "hidden" }}>
        <div
          style={{
            width: `${fillPercent}%`, height: "100%", borderRadius: theme.radius.pill,
            background: barColor, transition: "width .3s ease",
          }}
        />
      </div>
    </div>
  );
}
