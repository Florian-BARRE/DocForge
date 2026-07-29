---
name: architecture-conventions
description: Frontend structural conventions observed in src/docforge-rework/app/frontend — feature siloing and the grouped-primitives exception to one-component-per-file
metadata:
  type: project
---

`src/features/<name>/` slices do not import from each other. Every file under a feature imports
only from `api/`, `components/`, `theme.ts`, and `shell/` — never `../../features/<other>`. Keep
new feature work self-contained even when a sibling feature already has a similar widget (e.g.
`features/monitoring/ProgressBar.tsx` and `JobStatusChip.tsx` were not imported into
`features/collections/`; small local equivalents were written instead).

**Why**: this is the existing pattern across every feature directory (checked 2026-07-29, no
counter-examples) — presumably to keep feature slices independently movable/removable.

**How to apply**: when a new feature needs UI that resembles another feature's component, duplicate
a small local version rather than reaching across `features/` boundaries, unless the user says
otherwise.

---

General.md's "one component per file" rule tolerates a grouped-primitives file when several small
presentational components form one visual kit used together by a single feature's cards — e.g.
`features/collections/OverviewCardPrimitives.tsx` holds `StatTile`, `SummaryCard`, `Row` (this
pattern pre-existed as three co-located functions inside `CollectionOverview.tsx` before being
extracted verbatim into their own file).

**Why**: these primitives are meaningless in isolation and always consumed together by every card
in a given dashboard; splitting them into three files would add navigation overhead with no
SRP benefit.

**How to apply**: only for genuinely small (<15 line) presentational primitives that share one
call-site pattern within a feature. Anything with its own state, data fetching, or nontrivial
logic still gets its own file.
