// ====== Code Summary ======
// Read-only rendering of a collection's metadata schema — shared by the wizard's review step
// and the collection overview page, so both always agree on what a "schema" looks like.

import type { FieldSpec } from "../../api/collections";
import { theme as t } from "../../theme";
import { SchemaTableRow } from "./SchemaTableRow";

const headStyle: React.CSSProperties = {
  textAlign: "left", color: t.color.dim, fontSize: t.font.size.xs,
  padding: `${t.space.s}px ${t.space.m}px`, fontWeight: 600,
  textTransform: "uppercase", letterSpacing: "0.04em",
};

export function SchemaTable({ fields }: { fields: FieldSpec[] }) {
  if (!fields.length)
    return (
      <div
        style={{
          border: `1px dashed ${t.color.lineStrong}`, borderRadius: t.radius.l,
          padding: t.space.xl, textAlign: "center", color: t.color.dim, fontSize: t.font.size.m,
        }}
      >
        No fields declared.
      </div>
    );

  return (
    <div style={{ background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l, boxShadow: t.shadow.sm, overflow: "hidden" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${t.color.line}` }}>
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
          {fields.map((f) => <SchemaTableRow key={f.field_name} field={f} />)}
        </tbody>
      </table>
    </div>
  );
}
