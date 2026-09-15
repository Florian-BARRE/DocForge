// ====== Code Summary ======
// Settings ▸ Deployment — renders GET /capabilities: version/auth/GPU header, the reachable-
// services list, the per-family capability matrix, and a pointer to the raw Prometheus scrape
// endpoint (a text note, never an embedded dashboard — that's Grafana's job, not this UI's).

import { useEffect, useState } from "react";
import { getCapabilities, type CapabilitiesResponse } from "../../api/capabilities";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { theme as t } from "../../theme";
import { CapabilityMatrixGrid } from "./CapabilityMatrixGrid";
import { DeploymentServiceRow } from "./DeploymentServiceRow";

function gpuLabel(gpuPresent: boolean | null): string {
  if (gpuPresent === null) return "unknown";
  return gpuPresent ? "GPU present" : "CPU only";
}

export function DeploymentTab() {
  const [capabilities, setCapabilities] = useState<CapabilitiesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCapabilities()
      .then(setCapabilities)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, []);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!capabilities) return <LoadingState label="loading deployment info…" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: t.space.l }}>
      <div style={{ display: "flex", alignItems: "center", gap: t.space.m, flexWrap: "wrap" }}>
        <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.m, color: t.color.text }}>v{capabilities.version}</span>
        <Chip tone={capabilities.auth_enabled ? "ok" : "warn"}>{capabilities.auth_enabled ? "auth on" : "auth off"}</Chip>
        <Chip tone={capabilities.gpu_present ? "ok" : "neutral"}>{gpuLabel(capabilities.gpu_present)}</Chip>
      </div>

      <section>
        <h3 style={{ fontFamily: t.font.display, fontSize: t.font.size.m, color: t.color.text, marginBottom: t.space.s }}>Services</h3>
        {capabilities.services.length === 0 ? (
          <div style={{ color: t.color.dim, fontSize: t.font.size.s }}>No infra services reported.</div>
        ) : (
          <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, overflow: "hidden" }}>
            {capabilities.services.map((service) => (
              <DeploymentServiceRow key={service.name} service={service} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 style={{ fontFamily: t.font.display, fontSize: t.font.size.m, color: t.color.text, marginBottom: t.space.s }}>Available pipeline kinds</h3>
        <CapabilityMatrixGrid capabilities={capabilities.capabilities} />
      </section>

      <div style={{ color: t.color.mute, fontSize: t.font.size.xs, borderTop: `1px solid ${t.color.line}`, paddingTop: t.space.m }}>
        Raw Prometheus metrics for this deployment are served at <span style={{ fontFamily: t.font.mono }}>/metrics</span> — point a Prometheus/Grafana stack at it, this page doesn't embed a dashboard.
      </div>
    </div>
  );
}
