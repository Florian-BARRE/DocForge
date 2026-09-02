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
  /** True once the collection is confirmed to hold zero documents — the axis stays on screen but
   *  disabled, with a note explaining why ticking it wouldn't do anything yet. `undefined` while the
   *  document count hasn't loaded, treated the same as "has documents" (no premature disabling). */
  emptyCollection?: boolean;
}

/** Renders nothing when the collection has no searchable metadata field AND already holds documents
 *  — the content-only default needs no picker. An empty collection keeps the axis visible (disabled)
 *  instead, so a first-time user still sees WHERE a query would search once something is indexed. */
export function SearchTargetPicker({ fields, selection, onToggle, emptyCollection }: SearchTargetPickerProps) {
  const searchableFields = fields.filter((f) => f.semantic || f.lexical);
  if (searchableFields.length === 0 && !emptyCollection) return null;

  const emptyModalities = { semantic: false, lexical: false };

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.s,
        padding: theme.space.m, border: `1px solid ${theme.color.line}`,
        borderRadius: theme.radius.l, background: theme.color.surface,
        opacity: emptyCollection ? 0.6 : 1,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: theme.space.s, flexWrap: "wrap" }}>
        <span style={{ fontSize: theme.font.size.s, fontWeight: 600, color: theme.color.text }}>Search in</span>
        {emptyCollection && (
          <span style={{ fontSize: theme.font.size.xs, color: theme.color.mute }}>No documents indexed yet</span>
        )}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m }}>
        <TargetRow
          label="Content"
          supportsSemantic
          supportsLexical
          disabled={emptyCollection}
          value={selection[CONTENT_FIELD] ?? emptyModalities}
          onToggle={(modality, checked) => onToggle(CONTENT_FIELD, modality, checked)}
        />
        {searchableFields.map((field) => (
          <TargetRow
            key={field.field_name}
            label={field.field_name}
            supportsSemantic={field.semantic}
            supportsLexical={field.lexical}
            disabled={emptyCollection}
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
  disabled?: boolean;
  value: { semantic: boolean; lexical: boolean };
  onToggle: (modality: "semantic" | "lexical", checked: boolean) => void;
}

/** One target's name plus a checkbox per modality it actually supports — never the unsupported one. */
function TargetRow({ label, supportsSemantic, supportsLexical, disabled, value, onToggle }: TargetRowProps) {
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
        <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: theme.font.size.xs, color: theme.color.dim, cursor: disabled ? "default" : "pointer" }}>
          <input type="checkbox" disabled={disabled} checked={value.semantic} onChange={(e) => onToggle("semantic", e.target.checked)} />
          semantic
        </label>
      )}
      {supportsLexical && (
        <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: theme.font.size.xs, color: theme.color.dim, cursor: disabled ? "default" : "pointer" }}>
          <input type="checkbox" disabled={disabled} checked={value.lexical} onChange={(e) => onToggle("lexical", e.target.checked)} />
          lexical
        </label>
      )}
    </div>
  );
}
