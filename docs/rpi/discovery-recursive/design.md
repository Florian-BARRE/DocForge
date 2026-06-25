# Design — Recursive schema-driven discovery (unblocks a 100% discovery-driven UI)

> Status: FOR BUILD. Grounded by two read-only research passes (backend describe + frontend
> renderer), which independently converged on this contract. Prereq for the UI redesign.

## Problem (current state)
Discovery is a mix that CANNOT describe the full config:
- `_params_from_instance`/`_params_from_model` SKIP non-scalar fields (`_scalar_ui_type → None` for
  $ref/object/list-of-objects) → **gates, nested provider sub-configs, atomic, grouping/mmr dropped**.
- `pipeline.search.*` is not a registry "stage" → **entirely absent** from discovery.
- `Choice.fields` is `list[ParamSchema]` (scalars only, one level) → **no recursion**.
- Provider chains are typed `list[Any]` in the models → `model_json_schema()` shows NO union; the
  **registry (`get_configs(category)`) is the only source of provider choices**.
- Result: the search UI + gates are HAND-CODED (SearchStagePanel + sections), violating discovery-driven.

## The contract: a recursive `ConfigNode` tree
One `kind`-tagged node, emitted as `EndpointDescriptor.config_tree` (ADDITIVE — `dynamic_fields`
stays until the new renderer lands, then retired). Wire shape:

```
ConfigNode {
  path: str                 # full absolute dot-path, e.g. "pipeline.embed.gate.min_score"
  kind: "scalar" | "enum" | "object" | "chain" | "provider_union"
  label: str
  description: str
  default: Any
  resolved: bool            # false when a collection_id is needed but absent (badge, not per-leaf)

  # kind=scalar:
  type: "bool"|"int"|"float"|"str"|"secret"
  min / max: number | null

  # kind=enum:
  options: [str, ...]

  # kind=object:  (gates, atomic, contextualize, retrieve, grouping, mmr, query_transform, rerank)
  children: [ConfigNode, ...]      # recurse

  # kind=chain (multi) / provider_union (single, possibly optional):
  multi: bool                      # chain=true, single union=false
  optional: bool                   # union may be unset (adds a "disabled" choice)
  capability: str                  # registry category (parser/classifier/ocr/vlm/embed/rerank/llm/split_method)
  choices: [ ProviderChoice {
     id, label, available, selectable, default, note,
     params: [ConfigNode, ...]     # RECURSE — a provider's own fields, INCLUDING nested unions
  } ]
}
```
The single unlock: **`ProviderChoice.params: list[ConfigNode]`** (was `list[ParamSchema]`). That makes
`SemanticConfig.embed` (a provider-union inside a provider choice) expressible — nesting is uniform
and unbounded.

## Backend build (CHUNK D1)
- NEW `common_libs/pipeline/assembly/config_describer.py` — a `DescribeSurface` sibling: `describe(model_cls, field_category_map) -> ConfigNode`. Recursively walks `model.model_json_schema()`:
  - scalar/enum (incl. Optional anyOf, reuse extended `_scalar_ui_type`) → scalar/enum node.
  - `$ref`/object → `kind=object`, recurse children.
  - a field whose name is in the `field→category` map (the `Any`/`list[Any]` union fields) →
    `kind=chain` (list) or `provider_union` (single), choices from `get_configs(category)` with
    `availability()`/`merge_defaults()`/`selectable` (reuse `_auto_providers` logic); each choice's
    `params` = `describe()` of that provider config (RECURSE).
  - secrets via `_is_secret_key` → `type=secret`.
- The **field→category map** (the only glue, ~12 lines): ParseConfig.chain=parser; EnrichConfig.{classifier_chain=classifier, ocr_chain=ocr, vlm_chain=vlm}; ChunkConfig.split_method=split_method; SemanticConfig.embed=embed; EmbedConfig.{chain,sparse}=embed; SearchConfig.rerank.chain=rerank; QueryTransformConfig.llm=llm.
- `auto_import` must include `llm` + `rerank` (today's describe_stages list omits them).
- Emit `config_tree` for the config-bearing routes (create_collection, update_config) = describe(PipelineConfig). Keep collection-scoped `filters`/`weights`/`metadata` as their OWN resolver (schema-derived per collection — NOT folded into the recursive walk).
- ADD `config_tree: ConfigNode | None` to `EndpointDescriptor` (models.py). Keep `dynamic_fields` flat for now (additive). Retire `stage_descriptors.py` hand dict-literals + the non-scalar skip ONLY after the frontend cuts over.

## Frontend build (CHUNK D2)
- NEW `RecursiveFieldRenderer.tsx` consuming `ConfigNode[]`: scalar/enum→FieldInput; object→collapsible section + recurse; provider_union(single)→ProviderUnionPicker (today's SinglePicker); chain(multi)→ChainPicker (today's MultiPicker); weights/map→existing pickers.
- REUSE unchanged: `useConfigDraft`, `ConfigSaveBar`, `FieldInput`, Single/Multi pickers (renamed), WeightsPicker/MapPicker/MetadataFormPicker. Extract `readPath/setPath` to a shared util.
- `StageConfigPanel` unchanged (filter by `fieldPathPrefix`, `handleChange` nested patch, `extractInitialValue`) — it just calls RecursiveFieldRenderer instead of DynamicFieldsGroup.
- RETIRE after cutover: DynamicFieldsGroup, SearchStagePanel + Transform/Retrieve/Rerank/Embed sections + searchConfigHelpers, NestedProviderPicker hack + NESTED_PROVIDER_FIELDS, ScalarPicker wrapper. Search stages become normal discovery-driven panels (their `fieldPathPrefix` = pipeline.search.*).
- Add `theme.ts` (rules require it; today tokens live only in global.css) as part of the UI redesign.

## Sequencing
D1 backend (additive config_tree) → verify it describes the whole tree (gates+search+nested) →
D2 frontend renderer + cut search/ingestion panels onto it → retire flat path + hardcoded forms →
then the broader UI redesign (audit screens: monitoring, limits, users/grants, doc tracing, etc.).
