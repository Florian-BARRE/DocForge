// ====== Code Summary ======
// The audit trail's table shell — column headers + one AuditRow per entry. Server-ordered
// (newest first via the keyset cursor); no client-side sort, unlike DocumentStorageTable.

import type { AuditEntry } from "../../api/audit";
import { theme as t } from "../../theme";
import { AuditRow } from "./AuditRow";

const COLUMNS = ["Time", "Actor", "Method / Path", "Target", "Client / Correlation"];

export function AuditTable({ entries }: { entries: AuditEntry[] }) {
  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, overflow: "hidden" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
            {COLUMNS.map((label) => (
              <th
                key={label}
                style={{
                  textAlign: "left", color: t.color.dim, fontSize: t.font.size.xs,
                  padding: `${t.space.s}px ${t.space.m}px`, fontWeight: t.font.weight.semibold,
                  textTransform: "uppercase", letterSpacing: "0.04em",
                }}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <AuditRow key={entry.id} entry={entry} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
