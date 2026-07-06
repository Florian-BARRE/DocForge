// ====== Code Summary ======
// A field_name / value / origin table over a resolved metadata list — used by the document
// overview tab. Origin gets the same tone convention as the collection schema table.

import type { MetadataValue } from "../../../api/explorer";
import { Chip } from "../../../components/Chip";
import { theme } from "../../../theme";
import { ValueRenderer } from "./ValueRenderer";

const headStyle: React.CSSProperties = {
  textAlign: "left", color: theme.color.dim, fontSize: theme.font.size.xs,
  padding: `${theme.space.xs}px ${theme.space.s}px`, fontWeight: 400,
};
const cellStyle: React.CSSProperties = {
  padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s, verticalAlign: "top",
};

export function MetadataTable({ metadata }: { metadata: MetadataValue[] }) {
  if (!metadata.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No metadata recorded.</div>;

  return (
    <table style={{ borderCollapse: "collapse", fontSize: theme.font.size.s, width: "100%" }}>
      <thead>
        <tr style={{ borderBottom: `1px solid ${theme.color.line}` }}>
          <th style={headStyle}>Field</th>
          <th style={headStyle}>Value</th>
          <th style={headStyle}>Origin</th>
        </tr>
      </thead>
      <tbody>
        {metadata.map((m) => (
          <tr key={m.field_name} style={{ borderBottom: `1px solid ${theme.color.line}` }}>
            <td style={{ ...cellStyle, fontFamily: theme.font.mono }}>{m.field_name}</td>
            <td style={cellStyle}><ValueRenderer value={m.value} /></td>
            <td style={cellStyle}>
              <Chip tone={m.origin === "generated" ? "loop" : m.origin === "system" ? "warn" : "accent"}>{m.origin}</Chip>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
