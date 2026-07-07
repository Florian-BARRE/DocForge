---
name: metagen-embed-node-traps
description: S6 metagen + S7 embed node traps (docforge-rework shared engine) — chunk-metagen wholesale-overwrites generated_meta on chaining, duplicate targets silently dedupe, datetime schema hint dropped; F4 openai_compat factory has 7 consumers not 6
metadata:
  type: project
---

Audited 2026-07-04 on `rewrite/pipelines-node-engine`. Node code under `shared/libs/pipelines/ingest/nodes/metagen/` and `shared/libs/pipelines/nodes/embed/`. All CONFIRMED empirically; none block the happy path (single chunk-metagen + single embed) but they are latent.

- **Chunk-metagen wholesale-overwrites `generated_meta`.** `metagen/chunk/core.py` `run()` does `chunk.model_copy(update={"generated_meta": values})`, which REPLACES the dict. `MetagenChunkNode.UNIQUE_IN_GRAPH=False`, so two chunk-metagen nodes are wireable; node B drops node A's fields silently. Fix: merge — `update={"generated_meta": {**chunk.generated_meta, **values}}`. (`if values else chunk` returns the SAME instance, which is benign — counting uses `chunk.generated_meta` truthiness, not identity.)
- **Duplicate `targets` (same `field` twice) silently deduped.** `BaseMetagenNode._resolve_targets` doesn't reject dupes. COMBINED → `object_schema` dict-overwrites the property (first prompt lost, ONE call). PER_FIELD → TWO calls, last write wins (wasted spend, silent). Fix: raise in `_resolve_targets` on a repeated field name.
- **Datetime schema hint is dead + dropped.** `metagen/base/helpers.py` `_TYPE_SCHEMAS[DATETIME]` carries `"description_format":"ISO 8601"` but `object_schema` unconditionally `fragment.pop("description_format")` → the model is never told to emit ISO, yet `coerce` requires `datetime.fromisoformat`. Weakens datetime extraction; the key is dead. Fix: fold the format into the field description or emit JSON-schema `"format":"date-time"`.
- **Cross-scope explicit targets → silent zero.** A document node whose explicit `targets` all name CHUNK-scope fields resolves to `[]` and generates nothing, no warning (documented "one config serves both" — `__is_other_scope` skips them). Acceptable, but a WARN when non-empty explicit targets resolve to zero would catch a scope typo.
- **F4 factory has SEVEN consumers, not six.** `OpenAICompatConfig` is subclassed by: llm/openai_compatible, vlm/openai_compatible, enrich/figure_classify, contextualize/llm, chunk/semantic, embed/openai_compatible, metagen/base. PIPELINE.md §3e says "6 consommateurs" and omits embed/openai_compatible — doc drift. (5 use multiple inheritance `(BaseXxx, OpenAICompatConfig)`; figure_classify + metagen use single inheritance.)

**Verified-SAFE (don't re-flag):** pydantic MI keeps llm api_key required + vlm timeout 60 + others 30 + model required (no field-resolution drift); partial-sparse mid-run drops the WHOLE axis to None consistently (no misalignment); bge_server `response.json()` after `async with` close is safe (httpx eager-reads non-stream bodies); numeric-strip compacts only pure int/float lists >64 (bools/tuples/mixed preserved); `Chunk.generated_meta: dict[str,Any]` is a field inside an artefact, NOT a slot, so `describe()`/palette render all 27 cards fine.

**Why:** these are power-user / unusual-topology data-loss traps the validator doesn't catch, plus one prompt-quality gap.

**How to apply:** on ANY new per-chunk or per-item node that copies-and-updates an artefact, check REPLACE-vs-MERGE and whether the node is `UNIQUE_IN_GRAPH`. On any contract-target resolver, check duplicate/zero-resolution handling. Related: [[contextualize-llm-perchunk-traps]], [[pipeline-engine-edge-selection]].
