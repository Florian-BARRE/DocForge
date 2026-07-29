// ====== Code Summary ======
// The search-target picker for the Search Lab: choose WHERE the query searches — the chunk content
// and/or specific metadata fields — each on semantic (dense) and/or lexical (BM25) modality. Mirrors
// SearchFilterBuilder's shape but picks targets instead of filter values. Only ever offers a modality
// a field actually supports, so the selection it builds can never trigger the backend's 422.

import type { FieldSpec } from "../../api/collections";
import type { SearchTargetModel } from "../../api/search";
import { theme } from "../../theme";

/** Per-target modality ticks, keyed by field name (`CONTENT_FIELD` for the chunk body). */
export type TargetSelection = Record<string, { semantic: boolean; lexical: boolean }>;

export const CONTENT_FIELD = "content";

/** The selection that reproduces today's default behaviour — content, both modalities. */
export const DEFAULT_TARGET_SELECTION: TargetSelection = {
  [CONTENT_FIELD]: { semantic: true, lexical: true },
};

/**
 * Builds the `search_in` payload from a target selection.
 *
 * Returns `null` — deferring to the backend's own default — both when the selection is exactly
 * today's default (content, both modalities, nothing else) and when nothing is ticked anywhere,
 * which keeps this picker from ever sending an empty or all-false request.
 */
export function buildSearchIn(selection: TargetSelection): SearchTargetModel[] | null {
  const targets: SearchTargetModel[] = Object.entries(selection)
    .filter(([, modalities]) => modalities.semantic || modalities.lexical)
    .map(([field, modalities]) => ({ field, semantic: modalities.semantic, lexical: modalities.lexical }));

  const isDefault =
    targets.length === 1 && targets[0].field === CONTENT_FIELD && targets[0].semantic && targets[0].lexical;

  return targets.length === 0 || isDefault ? null : targets;
}

interface SearchTargetPickerProps {
  fields: FieldSpec[];
  selection: TargetSelection;
  onToggle: (field: string, modality: "semantic" | "lexical", checked: boolean) => void;
}

/** Renders nothing when the collection has no searchable metadata field — the content-only default needs no picker. */
export function SearchTargetPicker({ fields, selection, onToggle }: SearchTargetPickerProps) {
  const searchableFields = fields.filter((f) => f.semantic || f.lexical);
  if (searchableFields.length === 0) return null;

  const emptyModalities = { semantic: false, lexical: false };

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        padding: theme.space.m, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, background: theme.color.surface,
      }}
    >
      <span style={{ fontSize: theme.font.size.s, fontWeight: 600, color: theme.color.text }}>Search in</span>

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m }}>
        <TargetRow
          label="Content"
          supportsSemantic
          supportsLexical
          value={selection[CONTENT_FIELD] ?? emptyModalities}
          onToggle={(modality, checked) => onToggle(CONTENT_FIELD, modality, checked)}
        />
        {searchableFields.map((field) => (
          <TargetRow
            key={field.field_name}
            label={field.field_name}
            supportsSemantic={field.semantic}
            supportsLexical={field.lexical}
            value={selection[field.field_name] ?? emptyModalities}
            onToggle={(modality, checked) => onToggle(field.field_name, modality, checked)}
          />
        ))}
      </div>
    </div>
  );
}

interface TargetRowProps {
  label: string;
  supportsSemantic: boolean;
  supportsLexical: boolean;
  value: { semantic: boolean; lexical: boolean };
  onToggle: (modality: "semantic" | "lexical", checked: boolean) => void;
}

/** One target's name plus a checkbox per modality it actually supports — never the unsupported one. */
function TargetRow({ label, supportsSemantic, supportsLexical, value, onToggle }: TargetRowProps) {
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.s, color: theme.color.text,
        padding: `${theme.space.xs}px ${theme.space.s}px`, background: theme.color.surface2,
        border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.pill,
      }}
    >
      <span style={{ fontFamily: theme.font.mono, fontWeight: 600 }}>{label}</span>
      {supportsSemantic && (
        <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: theme.font.size.xs, color: theme.color.dim, cursor: "pointer" }}>
          <input type="checkbox" checked={value.semantic} onChange={(e) => onToggle("semantic", e.target.checked)} />
          semantic
        </label>
      )}
      {supportsLexical && (
        <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: theme.font.size.xs, color: theme.color.dim, cursor: "pointer" }}>
          <input type="checkbox" checked={value.lexical} onChange={(e) => onToggle("lexical", e.target.checked)} />
          lexical
        </label>
      )}
    </div>
  );
}
