# Discovery — per-endpoint, UI-buildable contract

`GET /api/v1/discovery` · `GET /api/v1/discovery?collection_id={uuid}`

The single endpoint a **100% dynamic UI** explores to build itself — zero hardcoded choices or
params. For **every** endpoint it returns the input/output contract **and**, for each free-form /
choice field, the available choices + the conditional fields each choice unlocks (e.g. provider →
its params), with **live deployment availability** and **collection-scoped** choices for search.

## How it's built (drift-proof by construction)

Two layers, stitched at request time — nothing hand-written per endpoint:

- **Contracts = FastAPI's own OpenAPI, verbatim.** The handler reads `request.app.openapi()`, walks
  `paths`, and copies `components` as-is. Every type / bound / default / required / enum is generated
  from the Pydantic models — identical to `/openapi.json` (what `/scalar` shows). It cannot drift.
- **Dynamic overlay = reuse of existing runtime sources.** Pipeline choices come from
  `ProviderRegistry.describe_stages()`; search/ingest choices come from the collection's metadata
  schema (`schema_field_dicts`, the same helper the search engine uses). The *only* hand-authored
  artifact is a ~6-line map `(route_function_name, field_path) → choice-source`
  (`backend/routers/discovery/overlays.py`), **validated against the live routes at startup** — a
  renamed handler fails fast, never silently.

## Response shape

```jsonc
{
  "openapi_version": "3.1.0",
  "collection_id": null,                       // echoed when ?collection_id given
  "endpoints": [
    {
      "operation": { "method": "POST", "path": "/api/v1/collections/create" },
      "route_name": "create_collection",
      "tags": ["collections"],
      "summary": "...", "description": "...",
      "path_params": [], "query_params": [],
      "input":  { "content_type": "application/json", "schema_ref": "#/components/schemas/CreateCollectionRequest" },
      "output": { "content_type": "application/json", "schema_ref": "#/components/schemas/ConfigStateResponse", "status": "201" },
      "dynamic_fields": [
        {
          "field_path": "pipeline.chunk.split_method",   // dot-path into the request body
          "capability": "chunk_strategy", "kind": "single", "scope": "deployment", "resolved": true,
          "choices": [
            { "id": "token_budget", "available": true, "selectable": true, "default": true,
              "fields": [ { "name": "max_tokens", "type": "int", "default": 512, "min": 64, "max": 4096 } ] },
            { "id": "semantic", "available": false, "selectable": true, "note": "TEI not reachable…", "fields": [ ... ] }
          ]
        }
        // … one per provider/method group: pipeline.parse.provider, pipeline.enrich.ocr_chain, pipeline.embed.provider …
      ]
    }
    // … all 28 endpoints; most have dynamic_fields: []
  ],
  "components": { "schemas": { /* verbatim OpenAPI components */ } }
}
```

`schema_ref` resolves against `components` exactly as a UI would against `/openapi.json`.

## Dynamic fields by endpoint

| Endpoint (route) | Field path | kind | scope | Choices from |
|---|---|---|---|---|
| `create_collection` | `pipeline.<stage.group.key>` | single/multi/optional | deployment | `describe_stages()` (providers + availability) |
| `update_config` | `patch.pipeline.<stage.group.key>` | single/multi/optional | deployment | `describe_stages()` |
| `search_collection`, `search_within_document` | `filters` | map | collection | filterable metadata fields → operator + value |
| `search_collection`, `search_within_document` | `weights` | weights | collection | named vectors (content + semantic/lexical fields) → float weight |
| `ingest_document` | `metadata` | map | collection | writable (non-system) metadata fields → typed value |

- **deployment-scoped** fields are always resolved (availability reflects installed packages /
  reachable services right now).
- **collection-scoped** fields (`filters`/`weights`/`metadata`) are `resolved: false` with no
  `collection_id`; re-request with `?collection_id=<uuid>` to get concrete choices derived from that
  collection's schema. The `weights` vectors are derived from the same `derive_vector_plan` the
  retrieval engine fuses, so they can't drift from what search honors.

## UI merge algorithm

```
form(method, path, collection_id?):
  ep   = discovery.endpoints[(method, path)]
  body = resolve(ep.input.schema_ref) in discovery.components      # JSON-Schema form
  for each property at dot-path fp in body:
    if ep.dynamic_fields has fp:  render the choice picker (selection → option.fields)
    elif property has enum:       render <select> (OpenAPI already enough)
    else:                         render scalar input (type/min/max/default from schema)
  output form/preview = resolve(ep.output.schema_ref)
```

## Notes

- `kind`: `single` = radio, `multi` = ordered list (e.g. OCR escalation chain), `optional` =
  nullable, `map` = key picker → value per chosen key (filters, ingest metadata), `weights` = one
  float per named vector. Disabled (`selectable:false`) options are shown greyed with `note`.
- ingest `metadata` is a `multipart/form-data` JSON-string field; the UI builds the object then
  serializes it into that field (OpenAPI types the wire field as `string`).
- `/capabilities` remains (pipeline-only view, already consumed/tested); `/discovery` is the
  superset surface and reuses the same builders.

## Tests

- `tests/api/discovery/test_discovery.py` — endpoints present, contracts ref components, pipeline
  overlay, search filters resolved/unresolved, overlay-key→real-endpoint drift guard.
- `tests/unit/test_discovery_overlays.py` — resolver logic + the startup route-key validator.
