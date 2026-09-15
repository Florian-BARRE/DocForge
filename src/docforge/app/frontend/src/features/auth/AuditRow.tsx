// ====== Code Summary ======
// One audit-trail row: time, actor, method+path with its status chip, target, and client
// ip/correlation id. Mirrors DocumentStorageRow's plain-<tr> styling convention.

import type { AuditEntry } from "../../api/audit";
import { theme as t } from "../../theme";
import { AuditStatusChip } from "./AuditStatusChip";

interface AuditRowProps {
  entry: AuditEntry;
}

const cellStyle: React.CSSProperties = { padding: `${t.space.s}px ${t.space.m}px`, fontSize: t.font.size.s, verticalAlign: "top" };
const monoCellStyle: React.CSSProperties = { ...cellStyle, fontFamily: t.font.mono, color: t.color.dim, whiteSpace: "nowrap" };

/** Shortens a long opaque id/token to its first 8 chars + ellipsis, full value on hover — the same
 *  "truncate id, let names lead" convention as everywhere else ids surface in this UI. */
function truncateId(value: string): string {
  return value.length > 10 ? `${value.slice(0, 8)}…` : value;
}

export function AuditRow({ entry }: AuditRowProps) {
  const target = entry.target_type
    ? `${entry.target_type}${entry.target_id ? `:${truncateId(entry.target_id)}` : ""}`
    : "—";

  return (
    <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
      <td style={monoCellStyle}>{new Date(entry.created_at).toLocaleString()}</td>
      <td style={{ ...cellStyle, color: t.color.text }}>{entry.actor_label ?? "—"}</td>
      <td style={cellStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: t.space.xs, flexWrap: "wrap" }}>
          <AuditStatusChip statusCode={entry.status_code} />
          <span style={{ fontFamily: t.font.mono, color: t.color.dim }}>{entry.method}</span>
          <span style={{ fontFamily: t.font.mono, color: t.color.text, wordBreak: "break-all" }}>{entry.path}</span>
        </div>
      </td>
      <td style={{ ...cellStyle, color: t.color.dim }} title={entry.target_id ?? undefined}>{target}</td>
      <td style={monoCellStyle} title={`${entry.client_ip ?? "—"} · ${entry.correlation_id ?? "—"}`}>
        <div>{entry.client_ip ?? "—"}</div>
        <div style={{ color: t.color.mute }}>{entry.correlation_id ? truncateId(entry.correlation_id) : "—"}</div>
      </td>
    </tr>
  );
}
