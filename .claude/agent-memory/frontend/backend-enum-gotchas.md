---
name: backend-enum-gotchas
description: Two backend enum surprises found while building the collections/monitoring UI — verify before trusting a "queued"/"enum" assumption
metadata:
  type: project
---

Two mismatches found 2026-07-04 while building the collections wizard + jobs monitoring UI,
against `shared/libs/public_models/contract.py` and `shared/libs/services/db/postgresql/tables/observability/job.py`
in `src/docforge-rework/`:

1. **`FieldType` has NO "enum" value.** The StrEnum is `string | integer | float | bool |
   keyword_list | datetime`. `enum_values` (a `list[str] | None`) is an orthogonal constraint that
   applies to ANY field type — the admission validator (`admission/helpers.py`) only actually
   checks membership for `string` (single value) and `keyword_list` (every item). The wizard's
   `FieldRow.tsx` gates the enum-values `TagsInput` on `field_type === "string" ||
   field_type === "keyword_list"` — a judgment call, not a backend-enforced rule, since nothing
   stops enum_values being set on an integer field (it would just never be checked).

2. **`JobStatus` is `pending`, not `queued`.** `jobs.ts`'s `JobStatusValue` type used to say
   `"queued" | "running" | "done" | "failed"` — fixed to `"pending" | "running" | "done" |
   "failed"` to match the real backend StrEnum (`Job.status`, default `PENDING`). The `| string`
   fallback kept it from being a hard type error either way, so this was a silent correctness bug,
   not a build failure.

**Why:** both were caught only by reading the actual Python enum source, not by trusting the
existing TS file — the pre-existing `jobs.ts` had drifted from the backend.

**How to apply:** before wiring UI logic (polling conditions, gating a control) to a string-enum
field from `api/*.ts`, grep the matching Python `StrEnum` in `shared/libs/` to confirm the literal
values, rather than trusting an existing TS annotation at face value.
