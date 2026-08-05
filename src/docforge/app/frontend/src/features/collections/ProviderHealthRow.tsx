// ====== Code Summary ======
// One provider row on the health board — its step, kind, probed endpoint host, a status dot+label,
// and latency when present. `not_configured` rows render dashed and dimmed (same "absence reads as
// absence" convention as `features/monitoring/WorkerCard`'s offline state), never a fourth colour.

import type { CSSProperties } from "react";
import type { ProviderHealth, ProviderStatus } from "../../api/collections";
import { theme as t } from "../../theme";

const COLOR_BY_STATUS: Record<ProviderStatus, string> = {
  ok: t.color.ok,
  unreachable: t.color.error,
  auth_failed: t.color.error,
  not_configured: t.color.mute,
  skipped: t.color.mute,
};

const LABEL_BY_STATUS: Record<ProviderStatus, string> = {
  ok: "up",
  unreachable: "unreachable",
  auth_failed: "auth failed",
  not_configured: "not configured",
  skipped: "skipped",
};

/**
 * Format a probed endpoint as a short host string for the board.
 *
 * @param endpoint - The secret-free base URL, `""` when the node inherits another node's endpoint,
 *   or `null` when the concept doesn't apply.
 * @param status - The row's reachability status, to distinguish "inherited" (ok, empty) from "—"
 *   (not configured, no endpoint at all).
 * @returns A scheme-stripped `host[/path]`, `"inherited"`, or `"—"`.
 */
function formatEndpoint(endpoint: string | null, status: ProviderStatus): string {
  if (endpoint === null || endpoint === "") return status === "ok" ? "inherited" : "—";
  try {
    const url = new URL(endpoint);
    const path = url.pathname === "/" ? "" : url.pathname;
    return `${url.host}${path}`;
  } catch {
    return endpoint;
  }
}

const CELL_ELLIPSIS: CSSProperties = { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };

interface ProviderHealthRowProps {
  provider: ProviderHealth;
}

export function ProviderHealthRow({ provider }: ProviderHealthRowProps) {
  const dashed = provider.status === "not_configured";
  const color = COLOR_BY_STATUS[provider.status];

  return (
    <div
      title={provider.detail ?? undefined}
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(90px, 1fr) 130px minmax(0, 1.6fr) 130px 60px",
        alignItems: "center",
        gap: t.space.m,
        padding: `${t.space.s}px ${t.space.l}px`,
        borderBottom: `1px ${dashed ? "dashed" : "solid"} ${t.color.line}`,
        opacity: dashed ? 0.65 : 1,
      }}
    >
      <span style={{ ...CELL_ELLIPSIS, color: t.color.text, fontSize: t.font.size.m, fontWeight: t.font.weight.medium }}>
        {provider.node_id}
      </span>
      <span style={{ ...CELL_ELLIPSIS, fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.dim }}>
        {provider.kind}
      </span>
      <span style={{ ...CELL_ELLIPSIS, fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.mute }}>
        {formatEndpoint(provider.endpoint, provider.status)}
      </span>
      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 7, height: 7, borderRadius: t.radius.pill, background: color, flexShrink: 0 }} />
        <span style={{ color, fontSize: t.font.size.s, fontWeight: t.font.weight.semibold }}>{LABEL_BY_STATUS[provider.status]}</span>
      </span>
      <span style={{ fontFamily: t.font.mono, fontSize: t.font.size.s, color: t.color.dim, textAlign: "right" }}>
        {provider.latency_ms !== null ? `${provider.latency_ms}ms` : ""}
      </span>
    </div>
  );
}
