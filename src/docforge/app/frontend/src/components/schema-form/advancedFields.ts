// ====== Code Summary ======
// The basic/advanced classifier behind SchemaForm's progressive disclosure. Before this, "Show
// technical details" only ADDED a type/default badge to every field — it never hid anything, so a
// stage's numeric tuning knobs (timeouts, retries, batch sizes…) sat on screen right next to its
// actual decisions (method/strategy pickers), which is the audit's core "4500px wall" complaint.
//
// The split is a NAME+TYPE heuristic over the schema itself, never a per-stage/per-field hardcoded
// list: a field is "advanced" only when it is NUMERIC (a decision is always an enum/select or a
// boolean — a strategy picker is never a plain number) AND its name reads as operational tuning.
// The keyword list mirrors the audit's own examples verbatim: timeout / retry(-ies) / backoff /
// batch / token(s) / coverage / cutoff / threshold. A numeric field that matches NONE of these
// (e.g. `max_concurrency`, `window_chunks`, `temperature`) stays BASIC — the safe default per
// "never hide something silently": under-hiding is recoverable (advanced toggle still reveals the
// type/default badge for it), over-hiding is not.

import type { JsonSchemaProperty } from "../../api/types";

const ADVANCED_NAME_RE = /timeout|retr(?:y|ies)|backoff|batch|token|coverage|cutoff|threshold/i;

/**
 * Whether one already-dereferenced schema property belongs in the "Show technical details" tier.
 *
 * Args:
 *   name: The property's key (the schema field name).
 *   resolved: The property, already run through `SchemaField.deref` (anyOf/$ref collapsed) —
 *     callers must deref first so a `X | None` numeric field is still recognised as numeric.
 *
 * Returns:
 *   bool: True when the field should stay hidden until advanced mode is toggled on.
 */
export function isAdvancedField(name: string, resolved: JsonSchemaProperty): boolean {
  const numeric = resolved.type === "number" || resolved.type === "integer";
  return numeric && ADVANCED_NAME_RE.test(name);
}
