// ====== Code Summary ======
// Pure helper: swap the filter value a search hint complained about for one of its suggestions,
// so the Search page can re-run with the corrected filter. Handles the scalar form, the list form
// (only the offending item is replaced) and an operator object (`{in: [...]}`, `{eq: v}`…).

import type { SearchHint } from "../../api/search";

function substitute(current: unknown, bad: unknown, replacement: string): unknown {
  if (Array.isArray(current)) return current.map((item) => (item === bad ? replacement : item));
  if (current !== null && typeof current === "object") {
    return Object.fromEntries(Object.entries(current).map(([op, inner]) => [op, substitute(inner, bad, replacement)]));
  }
  return current === bad ? replacement : current;
}

/** Return a copy of `filters` with the hint's offending value replaced by `suggestion`. */
export function applyHintSuggestion(filters: Record<string, unknown>, hint: SearchHint, suggestion: string): Record<string, unknown> {
  if (!(hint.field in filters)) return filters;
  return { ...filters, [hint.field]: substitute(filters[hint.field], hint.value, suggestion) };
}
