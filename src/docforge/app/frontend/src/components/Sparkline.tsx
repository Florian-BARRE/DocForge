// ====== Code Summary ======
// A tiny inline-SVG trend line — no charting dependency. Generic: the caller supplies the values and
// a theme-token stroke colour; this only handles the scaling/path math. Used for in-product job
// trends (done/h, failed/h, backlog) so the "history over time" view never depends on the optional
// Grafana overlay.

import { theme } from "../theme";

interface SparklineProps {
  values: number[];
  /** A theme-token colour string (e.g. theme.color.ok) — never a raw hex. */
  color: string;
  width?: number;
  height?: number;
  ariaLabel: string;
}

/** Maps `values` onto a flat 0..width / 0..height SVG viewbox, flat-lining the mid-height on a
 *  degenerate series (empty, or every bucket equal) instead of dividing by zero. */
function buildPoints(values: number[], width: number, height: number): string {
  if (values.length === 0) return `0,${height / 2} ${width},${height / 2}`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = values.length > 1 ? i * step : width / 2;
      const y = span === 0 ? height / 2 : height - ((v - min) / span) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function Sparkline({ values, color, width = 160, height = 32, ariaLabel }: SparklineProps) {
  const points = buildPoints(values, width, height);
  const last = values.length > 0 ? values[values.length - 1] : null;
  const lastPoint = points.split(" ").at(-1);
  const [lastX, lastY] = lastPoint ? lastPoint.split(",").map(Number) : [width, height / 2];

  return (
    <svg role="img" aria-label={ariaLabel} width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {last !== null && <circle cx={lastX} cy={lastY} r={2.5} fill={color} />}
      {values.length === 0 && (
        <text x={width / 2} y={height / 2 + 4} textAnchor="middle" fontSize={theme.font.size.xs} fill={theme.color.mute}>
          no data
        </text>
      )}
    </svg>
  );
}
