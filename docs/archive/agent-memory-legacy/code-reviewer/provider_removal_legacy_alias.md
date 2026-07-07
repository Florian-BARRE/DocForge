---
name: provider-removal-legacy-alias
description: Sanctioned pattern for removing a registered provider choice while keeping stored configs loadable (legacy id alias)
metadata:
  type: project
---

# Removing a provider CHOICE without breaking stored configs

Validated 2026-06-25 reviewing the `tei` EMBED removal, then again the `bge_reranker` RERANK removal (both collapsed into `bge_server`, same TEI HTTP client `BgeRerankProvider`/`TeiEmbedProvider` reused by the replacement's `.build()`). This is the canonical way to drop a registered provider id and should NOT be flagged when done this way.

**DRY follow-up (rerank change, approved):** the per-file inline `normalize_legacy_id` was extracted to a SHARED helper `common/.../config/pipeline/spec_utils.py` (`ProviderSpecHelpers` static-only class + module-level `flatten_provider_spec` / `normalize_legacy_id` wrappers). embed_config.py, semantic.py, and search_config.py all import it. Extraction is logic-identical → no embed regression. The earlier divergence note (point 5) is now resolved by sharing the function (each file still defines its OWN `_LEGACY_*_ID_ALIASES` map, which is fine). Minor non-blocking: `spec_utils.py` lacks `__all__`.

**RERANK specifics:** the alias lives on `RerankConfig._compat` (mode="before") in search_config.py and rewrites `rerank.chain[*]` UNCONDITIONALLY — independent of `enabled`. This matters: when `enabled=False` the mode="after" validator skips chain validation, but `_compat` already normalized the id, so no stale `bge_reranker` survives a resolve_pipeline round-trip and no raw legacy id can reach the union. `enabled` default stays False (rerank optional); `bge_server` is just the registered/canonical choice.

**Pattern (all parts required):**
1. Drop `@register("<cap>")` from the removed config; KEEP the class (unregistered) only as a back-compat reference. The shared HTTP client/provider stays exported and untouched.
2. Remove it from every hand-written discriminated union (`Annotated[A | B, Field(discriminator="id")]`) AND rely on `build_union(get_configs("<cap>"))` now excluding it.
3. Add a `_LEGACY_<CAP>_ID_ALIASES = {"old": "new"}` map + a `@model_validator(mode="before")` that rewrites `id` on EVERY chain entry AND the separate `sparse` backend, BEFORE the mode="after" union dispatch. Must run before the union so the old id never 422s.
4. The alias map must ONLY rewrite known legacy ids — an unknown id ("nope") must still reach the union and raise ValidationError (tests assert this).
5. Mirror the same rewrite in any OTHER config that embeds the same sub-union (e.g. the semantic chunker's `embed` sub-config). Watch for divergence — ideally reuse the same alias constant (the tei change inlined the literal in semantic.py; minor, flagged as non-blocking).

**Why it's safe — the four config paths all normalize:** create/update/rollback/read every funnel through `ConfigDocument.resolve_pipeline` → `PipelineConfig.from_dict(...).to_dict()` (`common/.../config/validation/document.py`), which runs the mode="before" normalizer (and recurses into `search.rerank`). The coherence validator (`ConfigValidator.validate`) runs on the post-`resolve_pipeline` doc, so it sees the NEW id. Search-builder embed derivation (`app/backend/libs/search/builder.py` `pipeline.embed.chain[0]`) and rerank build (`pipeline.search.rerank.chain[0]`, same file) consume an already-parsed `PipelineConfig`, so post-normalization too.

**Review checklist when you see a provider-choice removal:**
- mode="before" alias rewrite present + runs before the union? covers chain[*] AND sparse?
- carried-over fields share names with the replacement; replacement's extra fields default cleanly?
- no union anywhere still lists the removed config class (grep the class name)?
- unknown-id still rejects?
- rollback path re-normalizes the replayed snapshot (it does, via resolve_pipeline)?
