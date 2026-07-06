// ====== Code Summary ======
// Read-only rendering of a collection's metadata schema — shared by the wizard's review step
// and the collection detail page, so both always agree on what a "schema" looks like.

import type { FieldSpec } from "../../api/collections";
import { Chip } from "../../components/Chip";
import { theme } from "../../theme";

const headStyle: React.CSSProperties = {
  textAlign: "left", color: theme.color.dim, fontSize: theme.font.size.xs,
  padding: `${theme.space.xs}px ${theme.space.s}px`, fontWeight: 400,
};
const cellStyle: React.CSSProperties = { padding: `${theme.space.xs}px ${theme.space.s}px`, fontSize: theme.font.size.s };

function flag(active: boolean) {
  return <span style={{ color: active ? theme.color.ok : theme.color.dim }}>{active ? "✓" : "–"}</span>;
}

export function SchemaTable({ fields }: { fields: FieldSpec[] }) {
  if (!fields.length)
    return <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No fields declared.</div>;

  return (
    <table style={{ borderCollapse: "collapse", fontSize: theme.font.size.s, width: "100%" }}>
      <thead>
        <tr style={{ borderBottom: `1px solid ${theme.color.line}` }}>
          <th style={headStyle}>Name</th>
          <th style={headStyle}>Type</th>
          <th style={headStyle}>Req.</th>
          <th style={headStyle}>Filter</th>
          <th style={headStyle}>Lexical</th>
          <th style={headStyle}>Semantic</th>
          <th style={headStyle}>Enum values</th>
          <th style={headStyle}>Origin</th>
          <th style={headStyle}>Scope</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.field_name} style={{ borderBottom: `1px solid ${theme.color.line}` }}>
            <td style={cellStyle}>{f.field_name}</td>
            <td style={{ ...cellStyle, fontFamily: theme.font.mono }}>{f.field_type}</td>
            <td style={{ ...cellStyle, textAlign: "center" }}>{flag(f.required)}</td>
            <td style={{ ...cellStyle, textAlign: "center" }}>{flag(f.filterable)}</td>
            <td style={{ ...cellStyle, textAlign: "center" }}>{flag(f.lexical)}</td>
            <td style={{ ...cellStyle, textAlign: "center" }}>{flag(f.semantic)}</td>
            <td style={cellStyle}>
              {f.enum_values?.length
                ? f.enum_values.map((v) => <Chip key={v} tone="dim">{v}</Chip>)
                : <span style={{ color: theme.color.dim }}>—</span>}
            </td>
            <td style={cellStyle}>
              <Chip tone={f.origin === "generated" ? "loop" : f.origin === "system" ? "warn" : "accent"}>{f.origin}</Chip>
            </td>
            <td style={cellStyle}>{f.scope}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
