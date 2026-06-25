---
name: recursive-describer-vs-flat
description: Two parallel discovery describe surfaces (flat dynamic_fields vs recursive config_tree) can silently diverge on provider defaults
metadata:
  type: project
---

# Discovery has TWO describe surfaces — keep them honest about defaults

`common_libs/pipeline/assembly/` has two sibling describers that BOTH enumerate providers from
the registry but fill provider params differently:

- **flat** `describe.py::DescribeSurface._auto_providers` → emits `dynamic_fields`. Describes each
  provider from a `config_cls().merge_defaults(cfg)` **instance** → node defaults are DEPLOYMENT-MERGED.
- **recursive** `config_describer.py::describe(PipelineConfig, cfg)` → emits `config_tree` (CHUNK D1,
  additive). Describes each provider by walking the raw `config_cls` **JSON schema** → node defaults
  are STRUCTURAL only; `merge_defaults` is NEVER called despite the docstring claiming parity.

**Why it doesn't bite today:** every provider's URL/key is per-collection (project invariant — see
[[provider-config-per-collection]] / CLAUDE.md), and `merge_defaults` is a documented no-op for the
current providers (bge_server etc.). So structural == merged right now.

**How to apply:** when reviewing changes to either describer OR adding a provider whose
`merge_defaults` derives a value from `cfg` (deployment env), flag that the recursive `config_tree`
will show a WRONG default while the flat surface shows the right one. Either describe an instance
(`config_cls().merge_defaults(cfg)`) in the recursive path too, or keep the docstring honest that the
recursive tree intentionally surfaces structural defaults because deployment-config is per-collection.

**Field→category map is the only hand-glue** (`_FIELD_CATEGORY_MAP`): every `Any`/`list[Any]` union
field in the config models MUST be keyed `(ModelName, field)`. A missed union field renders as an
empty/object node (silent gap), not an error. Current complete set: ParseConfig.chain,
EnrichConfig.{classifier_chain,ocr_chain,vlm_chain}, ChunkConfig.split_method, SemanticConfig.embed,
EmbedConfig.{chain,sparse}, RerankConfig.chain, QueryTransformConfig.llm. Cross-check on any new union.

Secret safety: the recursive describer walks the model CLASS schema (never a populated collection
instance), so `default` is the structural field default — no stored secret can leak; secret-named
str fields are additionally tagged `type=secret`. Do NOT flag this path as a leak.
