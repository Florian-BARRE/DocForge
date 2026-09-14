// ====== Code Summary ======
// One infra store/sidecar row in the Deployment tab's services list — name, role, a reachability
// chip (ok/error status ink, never orange), device, and what it provides.

import type { CapabilityService } from "../../api/capabilities";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";

export function DeploymentServiceRow({ service }: { service: CapabilityService }) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: t.space.m, flexWrap: "wrap",
        padding: `${t.space.s}px ${t.space.m}px`, borderBottom: `1px solid ${t.color.line}`,
      }}
    >
      <span style={{ fontWeight: t.font.weight.semibold, color: t.color.text, minWidth: 120 }}>{service.name}</span>
      <span style={{ color: t.color.dim, fontSize: t.font.size.s, minWidth: 90 }}>{service.role}</span>
      <Chip tone={service.reachable ? "ok" : "error"}>{service.reachable ? "reachable" : "unreachable"}</Chip>
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.dim, minWidth: 50 }}>
        {service.device ?? "—"}
      </span>
      <div style={{ display: "flex", gap: t.space.xs, flexWrap: "wrap" }}>
        {service.provides.map((kind) => (
          <Chip key={kind} tone="dim">{kind}</Chip>
        ))}
      </div>
      {service.detail && (
        <span style={{ color: t.color.mute, fontSize: t.font.size.xs, marginLeft: "auto" }} title={service.detail}>
          {service.detail}
        </span>
      )}
    </div>
  );
}
