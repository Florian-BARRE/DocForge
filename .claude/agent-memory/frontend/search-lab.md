---
name: search-lab
description: Search Lab (UI-2) — tuning panel, debug panel, HttpError, useLabOverrides, overrides wiring
metadata:
  type: project
---

## Search Lab (UI-2)

### Types and hooks

- `components/search/labTypes.ts` — `SearchBaseline`, `SearchOverrides`, `SearchEffective`.
- `hooks/useLabOverrides.ts` — extracts baseline from `configState.pipeline.search.*`; tracks
  local choices as `Partial<SearchBaseline>`; computes `overrides` = only keys that differ from
  baseline. `isOverriding: boolean` gates the "Reset to config" button.

### Components

- `components/search/SegmentedControl.tsx` — generic `<SegmentedControl<T>>` using
  `.segmented-control / .segmented-btn / .segmented-btn-active` CSS classes.
- `components/search/LabTuningPanel.tsx` — collapsible panel; each control shows a baseline
  annotation ("config: hybrid") and a `.lab-override-dot` when overriding.
  "Reset to config" button only renders when `isOverriding`.
- `components/search/LabDebugPanel.tsx` — always-visible after a search (`debug: true` always
  sent). Reads `debug_info.effective` (new format) with fallback to flat `debug_info` keys.
  Shows effective chips, recall hint (candidates → top_k), collapsible query variants.

### Error handling

`api/client.ts` exports `HttpError extends Error` with `status: number`.
`handleError` throws `HttpError` for all non-401 errors.
`SearchTab` catches `instanceof HttpError && status === 422` → sets `labError` (shown inline
in `LabTuningPanel`); other errors → generic `searchError` banner.

### Client wiring

`api/client.ts` `searchDocuments` and `searchWithinDocument` accept `overrides?: SearchOverrides`.
`SearchTab.tsx` wires `useLabOverrides`, passes `overrides` (only when non-empty) and `weights`
to `searchDocuments`. Always passes `debug: true`. `SearchTraceSummary` was removed — `LabDebugPanel`
is the primary debug view.

### Vector names

Derived from `debug_info.dense_vectors + sparse_vectors` after first search.
Default before any search: `['content_dense', 'content_bm25']`.

### CSS (all in global.css)

`lab-tuning-panel`, `segmented-control`, `lab-effective-chip` (accent-tinted mono),
`lab-recall-hint`, `lab-422-banner` (red tint).

### Pre-existing polish (not UI-2 work)

`ConfigAppliedSummary.tsx` already renders `reindex_reasons[]` as a bulleted list under the
"Reindex required" tag. CSS class `.config-applied-reasons` in global.css.
