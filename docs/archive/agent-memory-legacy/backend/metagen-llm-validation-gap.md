---
name: metagen-llm-validation-gap
description: describe_stages does NOT expose the LLM category, so ProviderChecks can't validate metagen/query_transform providers
metadata:
  type: project
---

`ProviderChecks.build_provider_index` is keyed by `(capability, provider_id)` drawn from
`registry.describe_stages()` (in `common_libs/pipeline/assembly/stage_descriptors.py`). That descriptor
only emits groups for parse / classifier / ocr / vlm / split_method / embed — it does **NOT** emit the
`llm` category. Therefore `ProviderChecks` cannot validate the LLM chains used by `pipeline.metagen.chain`
or `pipeline.search.query_transform`.

**Why:** the metagen/query-transform LLM provider is surfaced to the UI only via the recursive
`config_describer` (`describe(PipelineConfig)`, `_FIELD_CATEGORY_MAP[("MetaGenConfig","chain")]="llm"`),
not via `describe_stages`. Adding a metagen loop to `ProviderChecks` would always emit
`metagen.unknown` because the index has no `("metagen"/"llm", ...)` entry.

**How to apply:** do NOT add an LLM/metagen loop to `ProviderChecks`. LLM provider validity is enforced
elsewhere: (a) the `MetaGenConfig` model_validator coerces each chain dict through `OpenAICompatLLMConfig`
→ ValidationError on unknown id at pipeline-parse time (422); (b) `MetagenChecks` (in
`common_libs/config/validation/validator/metagen_checks.py`) fires `metagen.no_provider` when there are
targets but an empty chain; (c) `ChainBuilderHelpers.build_metagen_chain` raises `ProviderUnavailableError`
at build time when base_url/api_key are missing. The preview endpoint translates that into a 422.

`MetagenChecks.check_metagen(doc, issues)` — signature is `(doc, issues)`, NOT the plan's `(doc, stages,
issues)`: it needs no `stages` because provider selectability is not its job (see above). Wired in
`validator/core.py` after `MetadataChecks`. Issue codes: `metagen.target_missing_field`,
`metagen.target_unknown_field`, `metagen.target_not_generated`, `metagen.duplicate_target` (errors),
`metagen.empty_prompt` (warning), `metagen.bad_scope` (error), `metagen.no_provider` (error),
`metagen.orphan_field` (warning).
