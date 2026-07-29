// ====== Code Summary ======
// A TABLE block rendered as a real <table> from its row-major cell grid — capped so a huge table
// doesn't dominate the reading-order list.

import type { IRTable } from "../../../api/explorer";
import { theme } from "../../../theme";

const MAX_ROWS = 15;

function cellText(cell: unknown): string {
  if (cell && typeof cell === "object" && "text" in cell) return String((cell as { text: unknown }).text ?? "");
  return cell === null || cell === undefined ? "" : String(cell);
}

export function TableBlock({ table }: { table: IRTable }) {
  const rows = Array.isArray(table.cells) ? (table.cells as unknown[][]) : [];
  const shown = rows.slice(0, MAX_ROWS);
  const hidden = rows.length - shown.length;

  return (
    <div>
      <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, marginBottom: 6 }}>
        {table.n_rows} × {table.n_cols}{table.has_header ? " · has header" : ""}
      </div>
      <div style={{ border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.s, overflow: "hidden", overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: theme.font.size.s, width: "100%" }}>
          <tbody>
            {shown.map((row, r) => (
              <tr
                key={r}
                style={{
                  borderBottom: r === shown.length - 1 ? "none" : `1px solid ${theme.color.line}`,
                  background: table.has_header && r === 0 ? theme.color.surface2 : "transparent",
                }}
              >
                {row.map((cell, c) => (
                  <td
                    key={c}
                    style={{
                      padding: "6px 10px", borderRight: c === row.length - 1 ? "none" : `1px solid ${theme.color.line}`,
                      fontWeight: table.has_header && r === 0 ? 600 : 400, color: theme.color.text,
                    }}
                  >
                    {cellText(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hidden > 0 && <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, marginTop: 6 }}>{hidden} more row(s)…</div>}
    </div>
  );
}
