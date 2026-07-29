---
name: ui-primitives
description: Reusable presentational primitives available under components/ and where feature-local variants live
metadata:
  type: project
---

`src/components/` holds the shared design-system primitives: `Chip` (tones accent|ok|warn|error|info|neutral|dim|loop),
`Button` (variant primary|secondary|ghost|danger, size sm|md), `FormField`, `inputStyle`, `TabNav` (generic `<K
extends string>` underline-tab strip — reusable as a segmented status filter, not just page tabs), `Switch`,
`ApiIssueList` (renders `HttpError.issues`), `PageHeader`, `ErrorState`, `LoadingState`.

**Why:** grepping this list before adding a new primitive avoids duplicating a segmented-control or badge that
already exists under a different name (e.g. `TabNav` doubles as an Active/Revoked/All filter, not just navigation).

**How to apply:** check `src/components/` first; only add a new primitive when none of the above fits, and put it
there (not feature-local) if it's not tied to one feature's domain types.

Related: `features/` never cross-import each other (confirmed convention, e.g. `collections/relativeTime.ts` vs a
separate local `auth/relativeTime.ts` — small helpers get duplicated per-feature rather than imported across
feature boundaries) — see [[feature-slice-isolation]].
