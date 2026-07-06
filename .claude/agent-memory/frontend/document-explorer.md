---
name: document-explorer
description: Document explorer feature (rework) — collection→documents→document tabs; per-tab lazy fetch cached at the page level; cross-tab jump-to-block
metadata:
  type: pattern
---

Shipped 2026-07-06 in `src/docforge-rework/app/frontend/src/features/explorer/`. Two new views
(`collection-documents`, `document`) added to `shell/view.ts`; `CollectionDetailPage` gained a
"Documents" action button alongside Edit collection/Edit pipeline/Jobs.

**Read-only browse surface for everything behind a document**: `DocumentsPage` (catalogue table,
two-step delete per row, same confirm pattern as `CollectionDetailPage`'s own delete) →
`DocumentPage` (header + hand-rolled tab nav: Overview/Pages/IR/Chunks). New generic
`components/TabNav.tsx` primitive (generic over a string literal union key) — reusable by any
future tabbed page, not explorer-specific.

**Lazy-fetch-per-tab, cached at the PAGE level, not the tab component level.** `DocumentPage` owns
`pages`/`ir`/`chunks` state and a `useEffect([activeTab, documentId])` that fetches each payload
only the first time its tab is activated (IR responses run ~1-2MB, chunks/pages are cheap but
still on-demand). Tab components (`OverviewTab`/`PagesTab`/`IRTab`/`ChunksTab`) are pure
presentational consumers of already-fetched data — this is deliberate: if the fetch lived inside
the tab component instead, conditionally unmounting it on tab-switch (`{activeTab === "x" && <Tab/>}`)
would drop the cache and refetch every time the user switched back. Because `DocumentPage` itself
follows the app's normal "page remount = free refetch" convention (see index), navigating to a
*different* document naturally resets the cache — no manual invalidation needed either way.

**Cross-tab "jump to block" (Chunks → IR) solved by keeping the target always mounted, not by
finding it after the fact.** `ChunkCard`'s block-id links call `onJumpToBlock(blockId)`, which sets
`focusBlockId` + switches `activeTab` to `"ir"`. `IRTab` renders EVERY block unconditionally and
uses a `visible` prop (CSS `display: none` vs `flex`) for the type filter instead of `.filter()`ing
blocks out of the array — this guarantees a `ref` map entry always exists for `focusBlockId`,
so `scrollIntoView` works even if the filter was hiding that block's type a moment ago. Two
effects: one resets the filter to `"all"` when `focusBlockId` changes, the second (dep
`[focusBlockId, typeFilter]`) does the actual `scrollIntoView` — it re-fires once the filter reset
lands and the block becomes visible (a `display:none` element is a scrollIntoView no-op).

**Value rendering by runtime shape, not by declared field type** — `metadata/ValueRenderer.tsx`
switches on `typeof value`/`Array.isArray` (bool → check mark, short array items ≤24 chars → Chip
row, longer array items → bullet list, object → inline JSON, else text), reused by
`metadata/MetadataTable.tsx` (document-level facts+metadata, Overview tab) AND
`metadata/ChunkMetadataBlock.tsx` (per-chunk metadata). A parallel `ValueRenderer` already exists
in the LEGACY tree (`detail-view.md`'s UI-3) — same idea, independently reimplemented here since
the rework tree has its own `api/explorer.ts` types; not a shared module across trees.

**Generated array metadata gets a distinct "showcase" component, not just a table row.**
`metadata/GeneratedFactsList.tsx` uses the `loop`/`loopSoft` token pair (already the app's
"non-standard/generated" accent, see `SchemaTable`'s origin-chip convention) to render a
`generated`-origin string-array field (e.g. metagen's `meta_gen` atomic propositions) as a
highlighted bullet-list callout inside `ChunkCard`, instead of burying it in a label:value line.

**Page/block numbering is 0-based on the wire despite the OpenAPI docstrings claiming "1-based"**
(`PageInfo.page_number`, `IRBlock.page` both start at 0 in real payloads). `features/explorer/format.ts`
exports `displayPage(n) => n + 1` and every page-number caption in the UI (pages grid, lightbox, IR
block chip) goes through it — a presentation-only transform, applied consistently everywhere so
the Pages tab and the IR tab's per-block page indicator always agree. Do not "fix" this by
assuming the wire value is already 1-based; it is not, in the current backend build.

**`api/explorer.ts`** is the new typed client (list/detail/pages/ir/chunks/delete + `blobUrl(hash)`
helper) — kept separate from `api/documents.ts` (upload-only contract) since the two REST surfaces
serve different features. Reuses `FieldOrigin` from `api/collections.ts` rather than redeclaring it.
