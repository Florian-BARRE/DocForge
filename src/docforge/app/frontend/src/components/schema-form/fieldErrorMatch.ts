// ====== Code Summary ======
// Best-effort tie between a build/inspect `ValidationIssue` and the ONE schema field it names, so a
// config form can ring the offending control instead of leaving the error floating in a banner
// above the whole rail. `location` never carries a node id for a pydantic-model validation error
// (see `humanizePydanticError`/`issuesFromBuildError` in api/http.ts) — only the model's own dotted
// field path (e.g. "candidate_multiplier", or "a.0.b" for a nested one). Matching the LAST path
// segment against a property name is therefore the most a purely client-side match can do; it is a
// display heuristic, not a routing contract — two different node schemas that happen to share a
// field name would both ring on the same issue, an accepted trade-off for a "polish" affordance.

import type { ValidationIssue } from "../../api/types";

export function fieldErrorMessage(issues: ValidationIssue[], fieldName: string): string | undefined {
  return issues.find((issue) => issue.location.split(/[./]/).pop()?.trim() === fieldName)?.message;
}
