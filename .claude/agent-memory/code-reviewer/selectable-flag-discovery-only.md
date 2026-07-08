---
name: selectable-flag-discovery-only
description: The SELECTABLE flag (P6a) hides internal wiring nodes from the palette method-picker; it is discovery-surface ONLY and must never leak into blob/graph/validation. Single chokepoint at NodeRegistry.catalog.
metadata:
  type: project
---

# `selectable` flag — the palette method-picker filter (P6a)

Chain: `AbstractNode.SELECTABLE` (class attr, default True) → `ActionNode.describe()` copies it →
`NodeDescription.selectable` → filtered ONLY in `NodeRegistry.catalog(family)`
(`return [card for card in cards if card.selectable]`).

## Invariants a reviewer must re-check on any new internal/wiring node
- **Single chokepoint.** `NodeRegistry.catalog` is the ONLY place internal kinds are dropped, and it
  has exactly ONE caller: `FamilyCatalog.from_family` (`introspection/catalog.py`). Both the lean
  (`PipelineCatalog.palette`) and full (`IngestPipeline.palette(full=True)`) palettes route through it,
  so both hide internal kinds. If a new palette path enumerates `kinds()` + `get().describe()` directly,
  it BYPASSES the filter — flag it.
- **`kinds()` / `get()` / `describe()` MUST still reach `SELECTABLE=False` nodes** — they are wired into
  graphs (prep/apply/skip/keep_raw terminals a stage builder emits), just not user-pickable. The
  explorer (`introspection/explorer.py`) uses `node.describe()` on a BUILT graph and correctly still
  shows them.
- **Zero leak beyond discovery.** `selectable` lives only on the describe() payload. It must NOT appear
  in the blob (Config-only), the graph build, or `GraphValidator`. Confirm no build/validation code
  reads `.selectable` / `.SELECTABLE`.

## The 8 kinds marked `SELECTABLE = False` (as of P6a)
metagen: `chunk_prep`, `document_prep`, `chunk_apply`, `document_apply`, `metagen_skip`;
contextualize: `llm_prep`, `llm_apply`, `keep_raw`. No user-pickable method (docling, bge_server,
doc_meta, breadcrumb, the real `contextualize/llm`, chunkers…) may be marked False — cross-check against
`test_design_surface.py::test_palette_hides_internal_kinds_but_keeps_them_registered`.

**Why:** P6a externalises `contextualize/llm`'s model call into a prep→ForEach(llm chain)→apply
topology; the prep/apply/keep_raw nodes are graph plumbing, not stage methods, so the palette must hide
them while the engine still resolves them.
**How to apply:** on ANY new prep/apply/skip/terminal node, verify SELECTABLE=False + the test asserts
it. On any new palette/discovery code path, verify it goes through `NodeRegistry.catalog`, not a raw
registry walk. Related: [[foreach-chain-terminal-item-type]], [[antipattern-chain-kind-raises]].
