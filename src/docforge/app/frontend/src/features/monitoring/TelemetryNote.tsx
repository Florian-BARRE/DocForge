// ====== Code Summary ======
// Informational card pointing at the full host-metrics dashboard — deliberately NOT a link, since
// the telemetry stack (Prometheus/Loki/Promtail/Grafana) is an OPTIONAL compose overlay
// (compose/overlays/compose.telemetry.yml) that may not be running for this deployment; hardcoding
// a Grafana host URL here would be a broken link on any install that didn't stack that overlay.

import { theme } from "../../theme";

export function TelemetryNote() {
  return (
    <div
      style={{
        background: theme.color.surface, border: `1px dashed ${theme.color.lineStrong}`,
        borderRadius: theme.radius.l, padding: `${theme.space.m}px ${theme.space.l}px`,
        color: theme.color.dim, fontSize: theme.font.size.s, maxWidth: 640,
      }}
    >
      <strong style={{ color: theme.color.text }}>Host metrics (CPU, memory, disk)</strong> live in the
      optional telemetry overlay's Grafana board (<span style={{ fontFamily: theme.font.mono }}>docforge-overview</span>),
      not here — this page only tracks job-level fleet health. Stack{" "}
      <span style={{ fontFamily: theme.font.mono }}>compose/overlays/compose.telemetry.yml</span> to enable it.
    </div>
  );
}
