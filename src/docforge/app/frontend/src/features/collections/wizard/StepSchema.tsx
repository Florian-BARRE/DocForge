// ====== Code Summary ======
// Wizard step 2: the metadata schema editor — a table of field rows, add/remove, then on to
// the review step. On creation the vector space is authored from scratch; in edit mode the
// backend diffs the submitted list against the stored schema by field name, so removing a row
// here deletes that field (and its stored values) once submitted — flagged inline below.

import { Button } from "../../../components/Button";
import { theme } from "../../../theme";
import type { WizardMode } from "./CollectionWizard";
import { FieldRow } from "./FieldRow";
import { blankField, type DraftField } from "./wizardTypes";

interface StepSchemaProps {
  mode: WizardMode;
  fields: DraftField[];
  onFieldsChange: (fields: DraftField[]) => void;
  onBack: () => void;
  onNext: () => void;
}

const headStyle: React.CSSProperties = {
  textAlign: "left", color: theme.color.dim, fontSize: theme.font.size.xs,
  padding: `${theme.space.s}px ${theme.space.s}px`, fontWeight: 600,
  textTransform: "uppercase", letterSpacing: "0.04em",
};

export function StepSchema({ mode, fields, onFieldsChange, onBack, onNext }: StepSchemaProps) {
  const valid = fields.every((f) =>
    f.field_name.trim().length > 0 && (f.field_type !== "enum" || Boolean(f.enum_values?.length)),
  );

  const updateAt = (index: number, field: DraftField) =>
    onFieldsChange(fields.map((f, i) => (i === index ? field : f)));
  const removeAt = (index: number) => onFieldsChange(fields.filter((_, i) => i !== index));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ background: theme.color.surface, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.l, boxShadow: theme.shadow.sm, overflow: "hidden" }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
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
              <th style={headStyle} />
            </tr>
          </thead>
          <tbody>
            {fields.map((field, index) => (
              <FieldRow key={field._key} field={field} onChange={(f) => updateAt(index, f)} onRemove={() => removeAt(index)} />
            ))}
          </tbody>
        </table>
        {fields.length === 0 && (
          <div style={{ color: theme.color.dim, fontSize: theme.font.size.s, padding: theme.space.l, textAlign: "center" }}>
            No fields yet — add at least one.
          </div>
        )}
      </div>
      {mode === "edit" && (
        <div style={{ color: theme.color.warn, fontSize: theme.font.size.xs }}>
          Removing a field here deletes it — and every value already stored for it — once you submit.
        </div>
      )}
      <div>
        <Button onClick={() => onFieldsChange([...fields, blankField()])}>+ Add field</Button>
      </div>
      <div style={{ display: "flex", gap: theme.space.s }}>
        <Button onClick={onBack}>Back</Button>
        <Button variant="primary" disabled={!valid} onClick={onNext}>
          Next — review
        </Button>
      </div>
    </div>
  );
}
