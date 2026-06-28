---
name: detail-view
description: Document detail view tabs, ValueRenderer, OverviewTab redesign (UI-3) — gotchas included
metadata:
  type: project
---

## Document detail view — tab layout

`DocDetailView.tsx` is the orchestrator; each tab is its own file under
`components/documents/detail/`:
- `OverviewTab` / `IRTab` / `ChunksTab` / `PagesTab` / `DownloadsTab` — pre-existing
- `ChainTracesTab` — renders `chain_traces` (parse/S1) and `embed_chain_traces` (S6) via
  `<ChainTraceView traces= variant='compact'|'detailed'>`.
- `JobsTab` — renders `doc.jobs[]` newest-first with expandable error rows.

`OverviewTab` accepts `onViewTraces?: () => void` — `DocDetailView` passes
`() => setActiveTab('traces')` so the "View in Chain traces tab →" button works.

CSS for jobs list in `global.css` under `/* ── Jobs Tab ──... */`.

## ValueRenderer (components/ui/ValueRenderer.tsx)

Generic recursive value renderer (189 lines). Three internal sub-components (not exported):
`HashValue`, `ArrayObjectValue`, `ObjectValue`.

Classification hierarchy (in order):
1. null / undefined / "" → muted "—"
2. boolean → badge (`✓ yes` / `✗ no`) using `.vr-bool-true` / `.vr-bool-false`
3. ISO timestamp string → `toLocaleString()`
4. hex hash string ≥32 chars → truncated `first7…last7` + clipboard copy button
5. storage path (contains "/" + known prefix `derived/`, `originals/`, etc.) → basename + title
6. number → `toLocaleString()`
7. array of all primitives → comma-joined
8. array with objects → count chip ("N items") + collapsible expand
9. plain object → field-count chip + collapsible KV block (recursive)
10. fallback → `String(v)` — never "[object Object]"

CSS classes (all in global.css): `.vr-bool-true/false`, `.vr-hash`, `.vr-hash-text`,
`.vr-copy-btn`, `.vr-count-chip`, `.vr-expand-list`, `.vr-expand-item`,
`.vr-obj-block`, `.vr-obj-k`, `.vr-obj-v`.

## OverviewTab redesign (UI-3)

`components/documents/detail/overviewMeta.ts` — pure constants + helpers (no JSX):
- `SKIP_IMPLICIT` — `Set<string>`: `chain_traces`, `embed_chain_traces` (shown in ChainTracesTab).
- `INTERNAL_IMPLICIT` — `Set<string>`: `ir_key`, `markdown_key`, `s0/s1/s2_fingerprint`.
- `LABEL` — acronym overrides: VLM/OCR/IR/S0-S6.
- `humanize(k)` — uses LABEL lookup, falls back to title-cased snake_case.
- `formatBudget(v)` — formats number as USD string (`$0.00` / `$0.0000` / `$0.00000`).
- `countArr(v)` — returns `v.length` if array, else 0.

`OverviewTab.tsx` sections: Identity / Content & structure / Processing /
User metadata / Advanced (collapsed toggle) / Chain traces summary.

`SectionBlock` sub-component defined OUTSIDE `OverviewTab` (avoids React remount anti-pattern).

Key patterns:
- `consumed: Set<string>` prevents any key rendering twice across sections.
- `lift(key)` tries `docR[key]` first, falls back to `meta[key]`, marks key consumed.
- `budget_spent` in implicit_meta formatted via `formatBudget()` (not raw ValueRenderer).
- Advanced section hidden behind `showInternal` useState toggle.

CSS: `.overview-section`, `.overview-internal-btn`, `.overview-traces-link` in global.css.

## Non-obvious gotchas (hard-won fixes)

**1. SectionBlock null-guard must include `!action`.**
The guard `if (!entries.length && !children && !action) return null` is critical.
Without `!action`, passing `entries=[]` (the collapsed initial state) makes SectionBlock
return null — the toggle button inside `action` is never mounted, so the Advanced section
disappears entirely even when internalEntries has data.

**2. `consumed` set must include ALL top-level field aliases from implicit_meta.**
The API mirrors many top-level `doc.*` fields in `implicit_meta` under the same or similar
key names. If they are not pre-consumed, they appear as duplicate rows in Processing.
Full list to consume: `filename, format, extension, language, status, file_size, id,
collection_id, created_at, page_count, block_count, chunk_count, n_blocks, n_figures,
n_tables, has_scanned_pages, quality_score, pipeline_version, pipeline_duration_ms,
indexed, has_original, has_markdown, has_pdf, source_hash`.

**3. `source_hash` routing.**
Use `docR['source_hash'] ?? meta['source_hash']` for the internalEntries value — NOT
`doc.source_hash`. The TypeScript `Document` type may not declare `source_hash`, and
for some document types the API only populates it inside `implicit_meta`.
`source_hash` must be in the `consumed` set so the loop skips it, but the explicit
fallback expression reads it directly from `meta` for the Advanced section.
