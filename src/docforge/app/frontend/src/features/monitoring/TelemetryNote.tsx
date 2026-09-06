// ====== Code Summary ======
// A small secondary footnote pointing at the full HOST-level metrics dashboard — deliberately NOT
// a link, since the telemetry stack (Prometheus/Loki/Promtail/Grafana) is an OPTIONAL compose
// overlay (compose/overlays/compose.telemetry.yml) that may not be running for this deployment;
// hardcoding a Grafana host URL here would be a broken link on any install that didn't stack it.
// Demoted to footnote status now that this page renders live per-worker CPU/mem itself — Grafana
// is only still useful for host-level history (disk, long-range trends), not live worker readout.

import { theme } from "../../theme";

export function TelemetryNote() {
  return (
    <div style={{ color: theme.color.mute, fontSize: theme.font.size.xs, maxWidth: 640 }}>
      Longer-range host history (disk, trends) lives in the optional telemetry overlay's Grafana
      board (<span style={{ fontFamily: theme.font.mono }}>docforge-overview</span>). Stack{" "}
      <span style={{ fontFamily: theme.font.mono }}>compose/overlays/compose.telemetry.yml</span> to enable it.
    </div>
  );
}
