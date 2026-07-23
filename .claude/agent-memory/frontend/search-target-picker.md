---
name: search-target-picker
description: SearchTargetPicker in the Search Lab — mirrors SearchFilterBuilder's shape but for WHERE the query searches (content + metadata fields, each on semantic/lexical); the null-elision default guard pattern.
metadata:
  type: project
---

Shipped 2026-07-23 in `src/docforge-rework/app/frontend/src/features/search/SearchTargetPicker.tsx`,
wired into `SearchLabPage.tsx` alongside `SearchFilterBuilder`. Lets the user restrict a query to the
chunk content and/or specific metadata fields, each independently on semantic (dense) and/or lexical
(BM25) — mirrors `SearchFilterBuilder`'s "renders nothing when the collection has nothing to offer"
shape, but the thing being picked is a search TARGET, not a filter value.

**The guard-rail pattern**: the backend 422s on a target naming an unsupported modality or a
selection with no modality ticked anywhere. The picker structurally can't build either — each field
only ever renders a checkbox for a modality it actually has (`FieldSpec.semantic`/`.lexical`), and
`buildSearchIn()` collapses BOTH "exactly today's default" (content, both modalities, nothing else)
AND "nothing ticked anywhere" to `search_in: null`, deferring to the backend's own default path. This
is a reusable trick worth repeating: when a picker's empty/default state must never desync from the
API's actual default, encode the elision as a pure function next to the component (`buildSearchIn`),
not as inline logic in the page — keeps the invariant testable/readable in one place.

**API type**: `SearchTargetModel = { field, semantic, lexical }` added to `api/search.ts`'s
`SearchRequest.search_in` — hand-mirrored from the backend Pydantic model per [[gen-types-constraint]]
(no live backend was used to regenerate).

**Correction folded into MEMORY.md**: while touching this feature, found `features/pipeline-editor/`
(the react-flow canvas) no longer exists in the tree — confirmed absent via `find`. The MEMORY.md
core-rules bullet describing it as "UNROUTED but kept for future advanced mode" was stale and has
been corrected. Pipeline UI is now just two studios: `features/stage-rail/` (ingest) and
`features/search-pipeline/` (search) — see [[search-pipeline]].
