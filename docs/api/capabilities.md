# Capabilities — discovery endpoint

`GET /api/v1/capabilities`

The single, **deployment-aware** discovery endpoint. A UI builds the entire collection
create/update configurator from this one call, and only ever offers what is actually available
**in this deployment** — availability reflects installed packages (e.g. PaddleOCR) and reachable
services (TEI, Qdrant, Mistral key set…), recomputed at request time.

No collection id, no auth state: it describes the *schema*, not a specific collection.

## Response

```jsonc
{
  "stages": [
    {
      "id": "s4", "label": "S4 · CHUNK", "name": "CHUNK", "description": "…",
      "params": [
        { "name": "chunk.hierarchical", "type": "bool", "label": "Hierarchical (parent/child)", "default": false, "description": "…" }
        // … atomic.*, cross_references, merge_short_sections, reinject_breadcrumb, heading_rules (type "rules")
      ],
      "groups": [
        {
          "key": "chunk.split_method", "kind": "single", "capability": "chunk_strategy",
          "label": "Section split method",
          "providers": [
            { "id": "token_budget", "label": "Token budget", "available": true, "selectable": true, "default": true, "note": "…",
              "params": [
                { "name": "max_tokens", "type": "int", "label": "max_tokens", "default": 512, "min": 64, "max": 4096 },
                { "name": "overlap_blocks", "type": "int", "default": 0, "min": 0, "max": 8 }
              ] },
            { "id": "semantic", "label": "Semantic (embeddings)", "available": false, "selectable": true,
              "note": "TEI not reachable at … — set base_url",
              "params": [ { "name": "max_tokens", "type": "int", "default": 512 }, { "name": "breakpoint_percentile", "type": "int", "default": 90, "min": 50, "max": 99 }, "…" ] },
            { "id": "sentence_window", "label": "Sentence window", "available": true, "selectable": true,
              "params": [ { "name": "window_sentences", "type": "int", "default": 5 }, "…" ] }
          ]
        }
      ]
    }
    // … s0 / s1 (parse provider) / s2 (enrich: classifier, ocr_chain, vlm) / s5 / s6 (embed provider)
  ],
  "metadata": {
    "field_types": ["string", "number", "date", "bool", "enum", "string[]"],
    "system_fields": [ { "field_name": "filename", "field_type": "string", "filterable": true, "lexical": true, "is_system": true }, "…" ]
  },
  "contract": {
    "locality_policies": ["on_premise_only", "external_allowed"],
    "unknown_field_policies": ["reject", "ignore", "store"],
    "default_embedding_model": "BAAI/bge-m3"
  },
  "defaults": { "parse": { "…": "…" }, "enrich": { "…": "…" }, "chunk": { "…": "…" }, "embed": { "…": "…" } }
}
```

## How a UI uses it

1. **Render the form** from `stages`: each `params` entry → a typed input (`bool`/`int`/`float`/`str`/`secret`/`rules`) bounded by `min`/`max` and pre-filled with `default`.
2. **Method/provider pickers** from `groups` (`kind`: `single` = radio, `multi` = ordered list, `optional` = nullable). Show each provider's `note`; **disable or warn** when `available=false` (e.g. semantic chunking when TEI is down), but it stays `selectable` if the URL/key can be supplied on the fly.
3. **Metadata editor** from `metadata.field_types` + `metadata.system_fields` (always present; the user only adds custom fields and may override a system field's flags).
4. **Contract form** from `contract` enums; pre-fill the pipeline with `defaults`.
5. Submit to `POST /collections/create` or `…/config/update` — the response echoes the resolved config + the `applied` transparency envelope.

The shapes here are exactly the values accepted by those endpoints, so the dot-path of each
`param` (`chunk.hierarchical`) or group `key` (`chunk.split_method`) maps 1:1 into the patch body.

## Model-driven (not hand-maintained)

The payload is **generated from the Pydantic models**, not curated by hand — so it can't drift:

- **`config_schema`** = `PipelineConfig.model_json_schema()` — the authoritative, exhaustive
  structural contract straight from Pydantic (every field, sub-model `$defs`, type, default, and
  `ge`/`le` bound → `minimum`/`maximum`). Add a field to a config model → it appears here, period.
- **`stages[].groups` split methods** are derived from the `SPLIT_METHOD_PARAMS` catalog (one
  Pydantic params model per method: `TokenBudgetParams`/`SemanticParams`/`SentenceWindowParams`).
  Each option's params (type, bounds, default, description) come from that model via
  `model_json_schema()`. The **same models validate** the params at build time in the registry —
  one source of truth for discovery + validation + construction.
- **Enums** (`field_types`, `locality_policies`, `unknown_field_policies`) are read from their
  actual sources (`MetaFieldType` / the `CreateCollectionRequest` Literals), never hardcoded.
- **`defaults`** = `PipelineConfig()` serialized.

> What Pydantic *cannot* express is the runtime layer: provider **availability** (is PaddleOCR
> installed? is TEI reachable?), per-provider free-form `params` for OCR/VLM/embed. That part lives
> in the registry overlay. Split-method params are already model-driven (above); extending the same
> self-describing pattern to the OCR/VLM/embed providers is the natural next step.

A drift-guard test (`tests/unit/test_registry_schema.py`) asserts the catalog equals the declared
`SPLIT_METHODS` and that the discovery params match the model fields.

## Tests

`tests/api/capabilities/test_capabilities.py` — shape, split-method options + param bounds,
metadata/contract catalog, resolved `defaults`, exposed `config_schema`.
`tests/unit/test_registry_schema.py` — catalog/source-of-truth drift guard + params derivation.
