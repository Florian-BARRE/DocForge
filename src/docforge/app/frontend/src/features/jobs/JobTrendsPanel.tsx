// ====== Code Summary ======
// In-product job trends — hourly done/h, failed/h and backlog sparklines from `/jobs/timeseries`, no
// Grafana dependency. Fills the SRE persona's "no historical view, only instantaneous scalars" gap.

import { SegmentedControl } from "../../components/SegmentedControl";
import { Sparkline } from "../../components/Sparkline";
import { theme } from "../../theme";
import { useJobTimeseries } from "./state/useJobTimeseries";

const WINDOW_OPTIONS = [
  { value: "24", label: "24h" },
  { value: "72", label: "72h" },
  { value: "168", label: "7d" },
];

interface TrendRowProps {
  label: string;
  values: number[];
  color: string;
  latest: number | null;
}

function TrendRow({ label, values, color, latest }: TrendRowProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.m }}>
      <div style={{ width: 90, fontSize: theme.font.size.s, color: theme.color.dim }}>{label}</div>
      <Sparkline values={values} color={color} ariaLabel={`${label} trend`} />
      <div style={{ width: 40, textAlign: "right", fontFamily: theme.font.mono, fontSize: theme.font.size.m, color: theme.color.text }}>
        {latest ?? "—"}
      </div>
    </div>
  );
}

interface JobTrendsPanelProps {
  windowHours: number;
  onWindowHoursChange: (hours: number) => void;
}

export function JobTrendsPanel({ windowHours, onWindowHoursChange }: JobTrendsPanelProps) {
  const { data, error } = useJobTimeseries(windowHours);

  const done = data?.buckets.map((b) => b.done) ?? [];
  const failed = data?.buckets.map((b) => b.failed) ?? [];
  const backlog = data?.buckets.map((b) => b.backlog) ?? [];

  return (
    <div
      style={{
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l, background: theme.color.surface,
        padding: theme.space.l, marginBottom: theme.space.l, display: "flex", flexDirection: "column", gap: theme.space.m,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m }}>
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l, color: theme.color.text }}>
          Trends
        </span>
        <SegmentedControl
          legend="Window"
          value={String(windowHours)}
          options={WINDOW_OPTIONS}
          onChange={(v) => onWindowHoursChange(Number(v))}
        />
      </div>
      {error && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>{error}</div>}
      {!error && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          <TrendRow label="Done/h" values={done} color={theme.color.ok} latest={data ? data.buckets.at(-1)?.done ?? null : null} />
          <TrendRow label="Failed/h" values={failed} color={theme.color.error} latest={data ? data.buckets.at(-1)?.failed ?? null : null} />
          <TrendRow label="Backlog" values={backlog} color={theme.color.warn} latest={data ? data.buckets.at(-1)?.backlog ?? null : null} />
        </div>
      )}
    </div>
  );
}
