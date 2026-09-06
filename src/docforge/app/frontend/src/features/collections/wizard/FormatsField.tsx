// ====== Code Summary ======
// The wizard's dedicated `supported_formats` control — a chip-multiselect over a curated common
// set (toggle on/off) plus free entry via the shared `TagsInput` for anything not listed. Pulled
// out of the generic schema-driven form the same way `MaxFileSizeField` already is (see
// StepIdentity's own `delete properties.supported_formats`): this field's UX (pick-a-format, not
// type-a-CSV-blob) is specific enough to earn a dedicated control rather than the generic
// string-array `TagsInput` render `SchemaField` gives every other array-of-string property.

import { useId } from "react";

import { Chip } from "../../../components/Chip";
import { TagsInput } from "../../../components/TagsInput";
import { theme } from "../../../theme";

// No backend discovery source exposes an accepted-formats vocabulary today — the closest thing,
// `DocumentAdmissionHelpers._FORMAT_EXTENSIONS` (app/backend/routers/documents/helpers.py), is a
// server-internal extension map, never surfaced over the API. This is therefore a deliberately
// curated FRONTEND fallback, not a mirrored backend default — flagged out of scope; the real fix
// is a `GET /formats` (or a contract-schema enum) discovery endpoint.
const SUGGESTED_FORMATS = ["pdf", "docx", "pptx", "html", "md", "txt", "png", "jpeg"];

/** Lowercases and strips any leading dots — ".PDF", "PDF", "pdf" all normalize to "pdf". */
function normalizeFormat(raw: string): string {
  return raw.trim().toLowerCase().replace(/^\.+/, "");
}

/** Normalizes a whole list and drops duplicates, preserving first-seen order. */
function normalizeFormats(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = normalizeFormat(value);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

interface FormatsFieldProps {
  values: string[];
  onChange: (values: string[]) => void;
}

export function FormatsField({ values, onChange }: FormatsFieldProps) {
  // Mirrors `SchemaField`'s own `<label htmlFor>` pairing (see components/schema-form/SchemaField)
  // so this dedicated control reads as part of the same form despite living outside SchemaForm.
  const controlId = useId();

  const toggle = (format: string) => {
    if (values.includes(format)) onChange(values.filter((value) => value !== format));
    else onChange(normalizeFormats([...values, format]));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: theme.font.size.s }}>
      <label htmlFor={controlId} style={{ display: "flex", alignItems: "baseline", gap: theme.space.xs + 2, color: theme.color.dim }}>
        <span style={{ color: theme.color.text }}>
          Accepted file formats
          <span style={{ color: theme.color.error }} title="required"> *</span>
        </span>
      </label>
      {/* 1. Selected chips + free-entry draft — normalizes on every change so a typed ".PDF" and a
         picked "pdf" chip below always collapse to the same token. */}
      <TagsInput
        id={controlId}
        values={values}
        onChange={(next) => onChange(normalizeFormats(next))}
        placeholder="Type a format and press Enter…"
        ariaLabel="Accepted file formats"
      />
      {/* 2. The multiselect — common formats as toggle chips, so a first-time user never has to
         guess the token syntax from a blank text box. */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {SUGGESTED_FORMATS.map((format) => {
          const selected = values.includes(format);
          return (
            <button
              key={format}
              type="button"
              onClick={() => toggle(format)}
              aria-pressed={selected}
              style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
            >
              <Chip tone={selected ? "accent" : "dim"}>{format}</Chip>
            </button>
          );
        })}
      </div>
      {/* 3. Help text, or — when empty — the field-level required message. The wizard's "Next"
         button already gates on this same emptiness check step-wide, but a message right under the
         control is what actually tells a first-time user WHY it's disabled. */}
      {values.length === 0 ? (
        <span style={{ color: theme.color.errorStrong, fontSize: theme.font.size.xs }}>
          Add at least one accepted format to continue.
        </span>
      ) : (
        <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs, lineHeight: 1.35 }}>
          Only files in these formats can be uploaded to this collection.
        </span>
      )}
    </div>
  );
}
