# DocForge REST API

The DocForge HTTP API drives the whole document-intelligence platform: create collections
(a contract = metadata schema + ingestion pipeline + search config), upload documents for
asynchronous ingestion, browse the parsed result, and run hybrid retrieval.

All examples below hit the **dev** API on `http://localhost:10040`. Adjust the host for your
deployment.

---

## 1. Overview

### Base URL & prefix

Every resource endpoint is mounted under the `/api/v1` prefix:

```
http://localhost:10040/api/v1/...
```

Two surfaces live **outside** `/api/v1` and are always public (no auth, see §2):

| Path | What it is |
|---|---|
| `GET /health` | Liveness probe. Returns `{"status": "ok"}` with HTTP 200. Never touches a store. |
| `GET /capabilities` | Deployment discovery — version, auth state, GPU presence, optional-sidecar reachability and the available pipeline kinds per family (see §16). |
| `GET /scalar` | Interactive API reference (the Scalar viewer) — reads the OpenAPI document client-side. |
| `GET /openapi.json` | The raw OpenAPI 3 schema (FastAPI default). |
| `GET /docs` | Swagger UI (FastAPI default). |

> The Scalar page is served at `/scalar` (not under `/api/v1`), so browse
> `http://localhost:10040/scalar` for the interactive docs.

### Content types

Everything is JSON in and JSON out, with two exceptions:

- **Document upload** (`POST /api/v1/documents`) is `multipart/form-data` (file + form fields).
- **Blob download** (`GET /api/v1/blobs/{hash}`) returns raw bytes with the blob's stored media type.

### Resource map

| Resource | Prefix | Section |
|---|---|---|
| API keys | `/api/v1/auth/keys` | §2 |
| Token self-introspection | `/api/v1/auth/whoami` | §2 |
| Collections | `/api/v1/collections` | §3 |
| Documents (admission) | `/api/v1/documents` | §4 |
| Explorer (browse) | `/api/v1/collections/{id}/documents`, `/api/v1/documents/{id}/...`, `/api/v1/chunks/...` | §5 |
| Document grid & bulk ops | `/api/v1/collections/{collection_id}/documents/query`, `…/delete`, `…/set-enabled`, `…/reingest` | §5 |
| Search | `/api/v1/collections/{id}/search` | §6 |
| Jobs | `/api/v1/jobs` | §7 |
| Blobs | `/api/v1/blobs/{hash}` | §8 |
| Pipelines (design) | `/api/v1/pipelines` | §9 |
| Config snippets (granular export/import) | `/api/v1/collections/{collection_id}/snippets/{kind}` | §10 |
| Config history (versions, diff, restore) | `/api/v1/collections/{collection_id}/config-versions` | §10b |
| Collection aliases (stable names, switch) | `/api/v1/collection-aliases` | §10c |
| Cost estimate (dry-run) | `/api/v1/collections/{collection_id}/estimate` | §11 |
| Pipeline preview (dry-run) | `/api/v1/collections/{collection_id}/pipeline/preview` | §11b |
| Collection transfers (export/import bundles) | `/api/v1/collections/{id}/export`, `/api/v1/collections/import`, `/api/v1/transfers/{transfer_id}` | §12 |
| Audit trail | `/api/v1/audit` | §13 |
| Idempotency (request header) | `Idempotency-Key` on mutating routes | §14 |
| Request correlation (response header) | `X-Request-Id` on every response | §15 |

---

## 2. Authentication

Auth is an **opt-in API-key bearer** model. It is **OFF by default** (`AUTH_ENABLED=false`),
in which case every request is silently treated as a full-access `root` and **no credential is
needed** — the dev default.

### Enabling auth

Set two environment variables and recreate the app container:

- `AUTH_ENABLED=true`
- `AUTH_ROOT_TOKEN=<some-long-secret>` — bootstrapped at startup into a full-access root key.

Once enabled, every `/api/v1/*` request must carry:

```
Authorization: Bearer df_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

Non-`/api/v1` surfaces (`/health`, `/scalar`, `/openapi.json`, `/docs`) stay public. Auth is
enforced by a pure ASGI middleware that runs **before** the request body is parsed, so a bad
credential is always a clean `401` (never a `422`-before-`401` on a malformed body).

The root token itself is a usable bearer. In practice you use it once to mint scoped keys, then
hand those out.

### The key model

A key carries two orthogonal scopes, stored as a `permissions` blob:

- **Capabilities** — the coarse action classes the key grants:
  `read_text`, `read_technical`, `write`, `search`, `create`, `admin`.
  Endpoints demand one of these (e.g. search requires `search`, upload requires `write`,
  creating a collection requires `create`, key management requires `admin`).
- **Collection scope** — either `["*"]` (every collection) or an explicit list of
  collection UUID strings and/or **`alias:<name>`** entries (see §10c). A scoped key is rejected
  `403` on any collection it does not list — including collections referenced in a form body, a
  query param, or via a document/chunk/blob.

**`alias:<name>` scope entries** follow the alias's **current** target: re-pointing the alias
re-scopes every key bound to it with no key edit. The alias is resolved on **every request**,
outside the authentication key cache (`AUTH_KEY_CACHE_TTL_SECONDS` caches the key row — hence the
alias NAME — never its target), so a re-point or a delete is effective on the very next request
(no TTL window). A deleted alias grants **nothing** (fail closed). At key create/rotate every
named alias must exist (`422` otherwise). A collection-scoped admin grants only scope entries it
**stores** itself — never an alias's current target as a pinned UUID (so a re-point cuts it off).
Revoking a key also evicts it from the authentication cache of the process that served the revoke.

Plus an optional **`expires_at`** (absolute instant; `null` = never expires).

A `permissions` of `null` means **full access** (the root shape) — it bypasses every capability
and scope check. `KeyPermissions` uses `extra="forbid"`; the `collections` wildcard `"*"` cannot
be mixed with explicit ids, and every explicit entry must be a valid UUID or `alias:<slug>`.

| Capability | Grants |
|---|---|
| `read_text` | The business read surface: list/get collections (the **lean** contract — `pipeline`/`search` blobs are `null` without `read_technical`), `describe`, document list/detail/query, markdown + html views, outline, chunks (always the lean shape — no `block_ids`/0-based `page` — without `read_technical`), chunk context, chunk browse, job list + job status. Without `read_technical`, the **search and chunk-browse hits never carry the drawing geometry** (`block_ids`, 0-based `page`, `bbox`, `block_locations`) — silently withheld even when `return_fields` names them; `page_number` (the citation) stays — and a job's `error` (job list/status) and a document's `failure_reason` have their URLs, `host:port` pairs and request paths replaced by `<redacted>` (`error_type`, `failed_node_id`/`failed_node_kind` and `current_stage` are never masked) |
| `read_technical` | The internals: IR, pages, provenance, the collection pipeline/search blobs, job events/payloads/stream, ops aggregates (stage durations, cost, queue, workers, failures, timeseries), collection health/storage/estimate, `/search/health`, the contract schema, the pipeline design routes (`/pipelines/*`), raw blobs, snippet export, collection export/transfers, config history (versions, diff), audit |
| `write` | Patch/delete collections, upload documents, toggle enabled, delete documents/chunks. A collection returned by `POST /collections` (`create`) or `PATCH /collections/{id}` (incl. `dry_run`) is the **lean** contract (`pipeline`/`search` `null`) unless the key also holds `read_technical`. The routes whose response is technical by nature — the collection-scoped stage apply (`…/pipeline/stages/apply`, a pipeline stage view) and the pipeline preview (`…/pipeline/preview`, `…/preview/jobs`, `…/preview/jobs/{id}`: IR summary + trace) — demand `write` **and** `read_technical` (`403` otherwise). Config-history restore needs only `write` (its response carries no blob) |
| `search` | Run collection search |
| `create` | Create collections. A **scoped** key that creates one is auto-granted ownership — the new collection id is appended to the key's own `collections` scope, so it can then manage what it created (per its other capabilities) without knowing ids in advance |
| `admin` | Manage API keys (create/list/revoke/rotate) |
| `read` *(legacy)* | The pre-split read capability. Still accepted on input and in stored keys: it is **normalized on load to `read_text` + `read_technical`**, so a key created before the split keeps its whole read surface with no data migration. Never returned by `whoami`; never demanded by a route |

**Usage profiles.** Instead of an explicit `capabilities` list, `permissions` may carry a named
`profile`; the server expands it and stores the explicit list (plus the `profile` label, for
display). Sending both is allowed only when they agree (`422` otherwise); sending neither is `422`.

| Profile | Capabilities | For |
|---|---|---|
| `agent_reader` | `read_text`, `search` | A business chatbot — reads documents as text and searches, sees no internals |
| `agent_searcher` | `search` | The narrowest retrieval key (hits already carry chunk text). Deliberately distinct from `agent_reader` rather than an alias of it |
| `operator` | `read_text`, `read_technical`, `write` | Operating collections and diagnosing ingestion |
| `admin` | every capability | Full power, still bounded by the key's `collections` scope (unlike a `null`-permissions root key) |

### 401 vs 403 semantics

- **401 Unauthorized** — no/invalid/revoked/expired bearer, or inactive owner. Carries
  `WWW-Authenticate: Bearer`. The failure detail is deliberately opaque (never reveals which
  check failed).
- **403 Forbidden** — the key authenticated fine but lacks the demanded capability, or is not
  scoped to the target collection, or has a malformed permissions blob.

### Key-management endpoints

**No escalation through key management.** Every key route needs `admin`. A full-access (root /
`null`-permissions) caller manages every key. A **scoped** admin key is held to keys whose scope is a
**subset of its own**: it may only grant capabilities it holds and collections it is scoped to, never
`permissions: null` (root-equivalent) and never `collections: ["*"]` unless it holds `*` itself; an
`alias:<name>` entry only when its own scope names that same alias (an alias follows re-points the
caller does not control). A create/rotate beyond that → `403`. `GET /auth/keys` lists only the keys
within the caller's scope; rotating or revoking a key beyond it → `403`. Key names `root` and
`anonymous` are reserved (they are config-history author labels) → `422`.

All require the `admin` capability. Keys are owned by the sole `root` account.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/keys` | Create a key — returns the plaintext **once** (`201`) |
| `GET` | `/api/v1/auth/keys` | List keys, newest first (metadata only) |
| `DELETE` | `/api/v1/auth/keys/{key_id}` | Soft-revoke a key (`204`, idempotent) |
| `POST` | `/api/v1/auth/keys/{key_id}/rotate` | Issue a fresh secret, revoke the old key (`201`) |

> The plaintext key is returned **only** at creation and rotation, in the `key` field. It is
> hashed at rest and can never be recovered — store it immediately.

**Create a scoped key** (the `agent_reader` profile, limited to one collection):

```bash
curl -sX POST http://localhost:10040/api/v1/auth/keys \
  -H "Authorization: Bearer $ROOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "reporting-service",
        "permissions": {
          "profile": "agent_reader",
          "collections": ["7f1c9d2e-4b8a-4c2f-9e3a-1a2b3c4d5e6f"]
        },
        "expires_at": "2027-01-01T00:00:00Z"
      }'
```

Response (`201`):

```json
{
  "id": "b1e2...",
  "name": "reporting-service",
  "prefix": "df_ab12cd34",
  "permissions": { "capabilities": ["read_text", "search"], "collections": ["7f1c9d2e-..."], "profile": "agent_reader" },
  "created_at": "2026-07-30T09:00:00Z",
  "expires_at": "2027-01-01T00:00:00Z",
  "key": "df_ab12cd34ef56...FULL_PLAINTEXT..."
}
```

A full-access key: omit `permissions` (or send `null`).

**Create a "project owner" key** (may create collections + full power over what it creates). Start
its scope empty; each collection it creates is appended to that scope automatically. This is the key
you hand to an agent (e.g. over MCP) to set up collections, then you mint a narrow `search`-only key
scoped to the resulting collection for your app's runtime:

```bash
curl -sX POST http://localhost:10040/api/v1/auth/keys \
  -H "Authorization: Bearer $ROOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "myproject-owner",
        "permissions": {
          "capabilities": ["read_text", "read_technical", "write", "search", "create"],
          "collections": []
        }
      }'
```

**Use the key** on any request:

```bash
curl -s http://localhost:10040/api/v1/collections \
  -H "Authorization: Bearer df_ab12cd34ef56..."
```

**Rotate** (every body field is optional; an absent field is cloned from the source key, a
provided `null` is meaningful — e.g. `permissions: null` re-scopes to full access):

```bash
curl -sX POST http://localhost:10040/api/v1/auth/keys/b1e2.../rotate \
  -H "Authorization: Bearer $ROOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "reporting-service-v2"}'
```

Rotation returns a new `CreatedKey` (new plaintext) and revokes the old key. A `404` means the
key is unknown; a `409` means it was already revoked (a terminal state).

### Token self-introspection

`GET /api/v1/auth/whoami` — the **calling token's own** access. It requires only authentication (no
capability), so even a `search`-only key may ask "what am I allowed to do" instead of discovering its
rights by collecting `403`s. Written for agents (MCP especially) that must plan before acting.

```bash
curl -s http://localhost:10040/api/v1/auth/whoami \
  -H "Authorization: Bearer df_ab12cd34ef56..."
```

Response is a `WhoAmI`:

```json
{
  "authenticated": true,
  "root": false,
  "capabilities": ["read_text", "search"],
  "collections": ["7f1c9d2e-4b8a-4c2f-9e3a-1a2b3c4d5e6f"],
  "profile": "agent_reader"
}
```

- `authenticated` — always `true` (an unauthenticated request never reaches this route).
- `root` — `true` for full, unscoped access: auth disabled, or a `null`-permissions key. Then
  `capabilities` lists every capability, `collections` is `["*"]` and `profile` is `null`.
- `capabilities` / `collections` — exactly what the key was granted (§"The key model"), normalized
  (a legacy `read` key reports `read_text` + `read_technical`).
- `profile` — the stored profile label, else the preset whose capability set matches exactly, else
  `null` (a custom set).

A key whose stored permissions blob is malformed is `403`, mirroring the authorization gate — never
a `500`.

---

## 3. Collections

A collection is the **contract**: a metadata schema + an ingestion pipeline blob + a search
config blob. The vector space is fixed at creation (named vectors cannot be added to Qdrant
later), so declare the **full** schema up front.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collections` | `read_text` | List all collections with their schema |
| `GET` | `/api/v1/collections/contract-schema` | `read_technical` | JSON Schema of the identity/limits contract (drives the create form) |
| `GET` | `/api/v1/collections/{id}` | `read_text` | One collection's contract — the `pipeline`/`search` blobs are `null` for a key without `read_technical` |
| `POST` | `/api/v1/collections` | `create` | Create a collection (`201`); a scoped creator is auto-granted ownership of it |
| `PATCH` | `/api/v1/collections/{id}` | `write` | Patch identity/limits/schema/config |
| `DELETE` | `/api/v1/collections/{id}` | `write` | Delete a collection (`204`) |
| `GET` | `/api/v1/collections/{id}/describe` | `read_text` | Lean agent guide: fields (meaning, type, real example values), valid `search_in` targets, filter grammar, example requests (`CollectionDescription`) |
| `GET` | `/api/v1/collections/{id}/health` | `read_technical` | Zero-spend provider preflight sweep + an overall verdict |
| `GET` | `/api/v1/collections/{id}/storage` | `read_technical` | Material footprint across all three stores (exact S3, estimated PG/Qdrant) |
| `POST` | `/api/v1/collections/{id}/reingest` | `write` | Re-run the full pipeline over the whole collection (`202`) |
| `POST` | `/api/v1/collections/{collection_id}/rebuild-index` | `write` | Rebuild the vector index from the current schema, no content re-embed (`202`, `RebuildIndexAccepted`) |
| `POST` | `/api/v1/collections/{id}/trace-payloads/purge` | `write` | Reclaim the collection's stored full execution-trace payloads (`TracePurgeResult`) |

### Schema changes on `PATCH /collections/{id}` (`fields` / `field_ops` / `dry_run`)

The metadata schema is edited either with the legacy full target list `fields` (matched by name — an
omitted field is **removed**, its values deleted) or with ordered `field_ops` (`add` / `update` /
`remove` / `rename`; a rename keeps the field's stored values). Sending both is a `422`. The response
carries a `schema_diff` (`added` / `modified` / `removed` / `renamed` / `values_lost` /
`reindex_required_fields`); a name freed by a rename and reused by an `add` in the same request is
reported as **added**. `reindex_required_fields` is checked against the vector store: on top of the
planner's verdict it lists every semantic/lexical field of the post-PATCH schema (the target schema
under `dry_run`) whose named vector Qdrant does not declare. The response also carries
`missing_vectors` (see below).

**Vector-store follow-through (both surfaces, including the legacy `fields` list).** After the commit
the Qdrant footprint (payload key + index, `meta_<slug>_*` vector data) of every name that **truly
left** the schema — removed or renamed away and not reused by the post-change schema — is purged from
every point, then the filter + meta-vector backfills are enqueued. A name still present after the
change (a swap A↔B, a remove A + rename B→A) is **never** purged. Remaining window, until the backfill
repaints a document: a renamed-to name has no payload yet (its filter matches nothing on that
document), and a reused name still carries its previous owner's value (the filter backfill then
overwrites it, and deletes it where the new owner has no value). Meta vectors of a reused name are
repainted only where the new owner has a value.

**`dry_run: true`** runs the request validation (shape, `fields`/`field_ops` exclusivity, every op,
per-field guards, vector-slug collisions, `title_field`, pipeline/search blob validation, secret
re-entry) and computes the `schema_diff` + `values_lost`, then writes nothing. The only write-time
error it cannot predict is a concurrent race: a collection rename losing the name-uniqueness race
(`409`).

### Purging stored trace payloads

`POST /api/v1/collections/{collection_id}/trace-payloads/purge` — capability `write`. Reclaims the
heavy per-node raw input/output bytes the opt-in `trace_verbosity='full'` tier stores in the object
store under each job's `trace/{job_id}/` prefix, and clears the stage-event rows' references so
nothing keeps advertising a payload that is gone. Only **terminal** jobs are reclaimed: an in-flight
(pending/running) job is skipped so the purge can never race that job's trace-finalize — its trace is
reclaimed once the job terminates (by a later purge or the retention GC). **Idempotent**: a collection
that stored nothing is a clean no-op returning zeros, not a `404` (only an unknown collection is
`404`). **Best-effort**: a storage error is swallowed server-side, so the call always succeeds and
reports the counts — it never returns a `500` for a partial store failure.

```json
{
  "purged_jobs": 12,
  "deleted_objects": 24
}
```

| Field | Type | Meaning |
|---|---|---|
| `purged_jobs` | int | Jobs in scope whose trace references were cleared (`0` when the scope has no jobs). |
| `deleted_objects` | int | Object-store objects removed across those jobs (`0` when nothing was stored). |

### The metadata FieldSpec

Each entry in `fields[]` declares one metadata field:

| Attribute | Type | Meaning |
|---|---|---|
| `field_name` | string | Unique name within the collection. Reserved names (Qdrant payload keys and `content`) are rejected `422`. |
| `field_type` | enum | One of `string`, `integer`, `float`, `bool`, `keyword_list`, `datetime`, `enum`, `text`, `integer_list`, `float_list`, `text_list`. |
| `required` | bool | Upload refused without it (user fields). Default `false`. |
| `filterable` | bool | Denormalized into the Qdrant payload → exact / any-of filter. Default `false`. |
| `lexical` | bool | Gets a sparse BM25 named vector. Default `false`. |
| `semantic` | bool | Gets a dense named vector. Default `false`. |
| `enum_values` | list[str]/null | Allowed values when `field_type` is `enum`. |
| `origin` | enum | `user` (declared at upload), `system` (pipeline), `generated` (metagen). Default `user`. |
| `scope` | enum | `document` (one value per doc) or `chunk` (one per chunk). Default `document`. |

Validation guards (all `422`):
- `chunk` scope is reserved for `generated` fields (users declare document-level metadata only).
- A `chunk`-scope field cannot be `lexical` (no BM25 producer for chunk metadata).
- A `field_name` cannot shadow a reserved chunk-payload key.

`needs_reindex` (read-only, on the response) is DERIVED, not sticky: it is `true` only when the
collection has already been indexed AND its current reindex-relevant config (the semantic/lexical
metadata surface + the embed vector space) differs from the config the indexed vectors were produced
under. A `filterable`-only change never sets it (the payload index is added live, no reindex);
reverting the config back to the indexed one clears it; and a successful (re)ingest advances the
baseline, so a real reindex turns it back to `false`. The exception is a store that still lacks a
semantic/lexical field's named vector. Qdrant cannot add a named vector to a live collection, so a
field made semantic/lexical after the first ingest has no vector yet. In that case the ingest leaves
the baseline untouched and keeps `needs_reindex: true`. A reingest does NOT add the vector; only an
index rebuild does (`POST /collections/{id}/rebuild-index`, below).

`missing_vectors` (read-only) lists those undeclared named vectors (`meta_<slug>_dense` /
`meta_<slug>_bm25`). It is computed by `GET /collections/{id}` and on the `PATCH` response (`[]` =
aligned or never ingested), and is `null` on the fleet list, which never reads the vector store.

### Config blobs

- `pipeline` — the ingestion graph blob. Omit on create to get the validated product default.
  Validated (auto-healed to the current engine + structurally checked) before storage; a broken
  graph is `422` and never reaches the worker.
- `search` — the search graph blob. `{}` = use the stock default. A non-empty blob must carry a
  `nodes` list and be a valid search pipeline (must terminate on a `SearchResult`), else `422`.

Both blobs are large and opaque; treat them as produced/edited via the pipeline design surface
(§9) rather than hand-written. Reads strip an internal version stamp so the blob is clean to
post back.

### Estimate overrides

`GET /api/v1/collections/{id}` returns `estimate_overrides` (nullable); `PATCH` accepts it to
tune the cost-estimate rate model (§11) for that one collection. `null` means "use the global
defaults" everywhere.

`EstimateOverrides` is a partial, deep-merged patch over the global defaults — every field is
optional and only the ones you set are overridden:

```json
{
  "rates": {
    "models": { "gpt-4o-mini": { "input": 0.15, "output": 0.60 } },
    "embed": { "bge-m3": 0.0 },
    "ocr": { "mistral": 1.0 }
  },
  "assumptions": {
    "tokens_per_page": 500,
    "bytes_per_token": 4,
    "bytes_per_page": 2048,
    "target_chunk_tokens": 400,
    "chunk_overlap_ratio": 0.15,
    "images_per_page": 0.3,
    "scanned_page_ratio": 0.1,
    "llm_prompt_overhead_tokens": 200,
    "llm_output_tokens": 300,
    "metagen_doc_context_tokens": 500,
    "metagen_output_tokens_per_field": 50,
    "vlm_prompt_tokens_per_image": 300,
    "vlm_output_tokens": 200,
    "embed_dense_dims": 1024
  }
}
```

- `rates` — dollar rates keyed by provider/model id, overriding the canonical pricing table:
  `models` (per-1K-token input/output for LLM/metagen stages), `embed` (per-1K-token embed cost),
  `ocr` (per-page OCR cost). Rates carry no secrets, only numbers. Local in-stack providers
  (`bge_server`, RapidOCR, Paddle) always cost `0`; an unrecognized paid model with no rate (here
  or in the canonical table) reports a **null** cost, never a fabricated number.
- `assumptions` — the sizing knobs the estimator uses when it can't read exact numbers off a
  document (page/token ratios, chunk sizing, image density, per-stage prompt/output token
  overhead, embedding dimensionality).

Both objects are optional and every leaf inside them is optional; an omitted leaf falls back to
the global default for that value.

### Discover the contract schema

`GET /api/v1/collections/contract-schema` — capability `read_technical`. Returns the **full discoverable
vocabulary** of a collection contract, so a purely-HTTP client (e.g. the MCP) never has to guess a
value and learn it was wrong at a `422`. Three parts, each serialized from the canonical server source
(never a hand-copied literal):

- `config_schema` — the **JSON Schema** of the identity/limits contract (`name`, `supported_formats`,
  `max_file_size_bytes`, `job_timeout_seconds`, `preset`), the same model `POST /api/v1/collections`
  composes, so the two can never drift. A UI feeds it straight to a schema-driven form.
- `field_schema` — the **JSON Schema** of one metadata `FieldSpec`; its `$defs` carry the valid
  `field_type` / `origin` / `scope` enum values the scalar contract omits.
- `supported_format_tokens` — every upload format token a collection may declare in
  `supported_formats` (e.g. `pdf`, `docx`, `md`).

```json
{
  "config_schema": { "title": "CollectionContractModel", "type": "object", "properties": { "...": {} } },
  "field_schema": { "title": "FieldSpecModel", "$defs": { "FieldType": { "enum": ["string", "integer", "..."] } } },
  "supported_format_tokens": ["csv", "doc", "docx", "html", "jpeg", "md", "pdf", "png", "txt", "..."]
}
```

The metadata schema (`fields[]`) is not part of `config_schema` — its shape and enum vocabulary are
served in `field_schema` (and described in "The metadata FieldSpec" above).

### Create a collection

```bash
curl -sX POST http://localhost:10040/api/v1/collections \
  -H "Content-Type: application/json" \
  -d '{
        "name": "contracts",
        "supported_formats": ["pdf", "docx"],
        "tags": ["legal", "demo"],
        "max_file_size_bytes": 52428800,
        "fields": [
          {"field_name": "client", "field_type": "string", "required": true, "filterable": true},
          {"field_name": "year", "field_type": "integer", "filterable": true},
          {"field_name": "summary", "field_type": "text", "origin": "generated", "semantic": true}
        ]
      }'
```

Returns the created `CollectionModel` (`201`). `409` on a name clash, `422` on a bad pipeline or
colliding vector slugs. `tags` is an optional list of free-form labels for grouping/filtering
collections in the UI; omit it (or pass `[]`) to create the collection untagged. The response always
carries `tags` (`[]` when untagged).

**Business presets.** When you omit `pipeline`, the ingestion blob is seeded from the `preset`
selector; `search_preset` seeds the collection's search blob. Each preset is a curated,
validation-passing stock topology (not a new engine) with every provider-hosted stage OFF. Discover
the available presets — name, label and rationale — from the design surface: `GET
/api/v1/pipelines/ingest` and `GET /api/v1/pipelines/search` each return a `presets` array.

- `preset` (ingestion, ignored when `pipeline` is set): `standard` (default full pipeline), `light`
  (fast, local, enrichment-free core), `ocr_scan` (a local OCR pass for scanned/image documents),
  `high_precision` (finer chunks for sharper hybrid retrieval).
- `search_preset`: `hybrid` (default dense+sparse fusion), `hybrid_rerank` (hybrid then a
  cross-encoder rerank), `dense_only` (pure semantic retrieval). Omitted → the stock hybrid default.

```bash
curl -sX POST http://localhost:10040/api/v1/collections \
  -H "Content-Type: application/json" \
  -d '{"name": "scans", "supported_formats": ["pdf"], "max_file_size_bytes": 52428800,
       "preset": "ocr_scan", "search_preset": "dense_only"}'
```

### Patch a collection

`PATCH` is partial. `fields` is applied by **diff** (fields matched by name; omitted fields are
removed; existing values survive untouched fields). `tags` is replaced **wholesale** when supplied
(`[]` clears every label); omit it to leave the labels unchanged. A `note` records a version snapshot.

```bash
curl -sX PATCH http://localhost:10040/api/v1/collections/7f1c9d2e-... \
  -H "Content-Type: application/json" \
  -d '{"tags": ["legal", "archived"], "max_file_size_bytes": 104857600, "note": "raise upload ceiling to 100 MB"}'
```

Each `fields[]` entry may carry an optional `description` (max 1000 chars — what the field means;
surfaced by `/describe`). The collection carries an optional **`title_field`**: the name of a
**document-scope** field whose value becomes each document's `display_title` (read-time only — no
re-ingest). On create/PATCH it must name a document-scope field of the (post-PATCH) schema, else
`422`; on PATCH, omitted = unchanged and an explicit `null` clears it; it is auto-cleared when a
schema PATCH removes, renames or moves that field to chunk scope. `GET` collection responses mask
every provider secret in the `pipeline`/`search` blobs as the constant `__redacted__` (no suffix);
echoing `__redacted__` (or an older `__redacted__<last4>` form) back in a PATCH keeps the stored
secret.

### Describe a collection (agent guide)

`GET /api/v1/collections/{collection_id}/describe` (READ, collection-scoped; 404 if unknown) — a
compact agent-oriented guide to one collection: `collection_id`, `name`, `document_count`,
`title_field`, `page_numbering` (which page field to cite), `fields[]` (`name`, `type`, `description`,
`scope`, `origin`, `filterable`, `semantic`, `lexical`, `required`, `enum_values`, `example_values` —
up to 10 real stored values, most frequent first — `distinct_count`, `note`),
`searchable_targets[]` (the valid `search_in` entries `{field, semantic, lexical}`), `filter_grammar[]`
(the accepted filter value forms) and `example_requests[]` (ready-to-send search bodies built from the
collection's real fields). It never includes pipeline/search config or secrets.

The guide is cached in-process per collection (bounded LRU). A cached guide is served only while the
collection's change stamp (its `updated_at`, its document count and its documents' latest
`updated_at`) is unchanged — an ingestion, a document delete, a metadata value edit
(`PATCH /documents/{id}/metadata`) or a collection/schema PATCH refreshes it on the next call — and
never beyond `DESCRIBE_CACHE_TTL_SECONDS` (default 30 s; `0` disables the cache).

### Rebuild the index

`POST /api/v1/collections/{collection_id}/rebuild-index` — capability `write`, no body. Answers `202`
with a `RebuildIndexAccepted` `{collection_id, job_id}`. Poll `GET /api/v1/jobs/{job_id}`: the job's
`kind` is `rebuild_index` and its `document_id` is `null` (a rebuild belongs to the collection, not
to a document).

Use it when `missing_vectors` is not empty, that is, when a field was made semantic or lexical after
the first ingest. It is also the way to give an older collection's metadata BM25 vectors the IDF
modifier. Content vectors are copied as they are and never re-embedded. The metadata vectors are
refilled from Postgres: the lexical ones are encoded locally, but the dense metadata values go through
the collection's embed provider (a small, but billed, provider call).

How it works:

1. The worker waits for the collection's other live jobs to finish, up to
   `WORKER_REBUILD_INDEX_WAIT_SECONDS`. If they are still running after that, the job fails without
   touching the index.
2. It creates a new physical Qdrant collection `col_<hex>_r<ts>` from the CURRENT schema. It copies
   every point into it, in batches of `WORKER_REBUILD_INDEX_BATCH_SIZE`, and drops every
   `meta_*_bm25` vector on the way (they are re-encoded at step 4). Between batches, and once more
   right before the swap, the job re-reads its own row: a cooperative cancel (or a reaper that turned
   the row terminal) stops it there, the new collection is deleted and the job ends `cancelled` (a
   reaped row stays `failed`). If
   anything fails before the swap, the new collection is deleted and the old index stays live and
   untouched. A finished copy is stamped **complete** (Qdrant collection metadata) before the swap.
3. It swaps the stable name `col_<hex>` onto the new collection. After this, `col_<hex>` is a Qdrant
   **alias**. Later rebuilds re-point the alias in one atomic call, then delete the old physical
   collection. **Gap on the first rebuild:** the stable name is a real collection at that point, and
   an alias cannot shadow it. So the first rebuild deletes the old collection, then creates the alias
   (retried a few times). A search that lands between those two calls sees an empty index (a window
   of milliseconds). If the worker crashes inside that window, every path that addresses the store
   (ingest, search, browse, export, metadata sync) re-points the alias at the newest **complete**
   generation on first access; a partial (unstamped) copy is never adopted.
4. It refills the filter payloads and the metadata vectors from Postgres, re-applies each chunk's
   `enabled_override`, and deletes the points of documents deleted during the copy.
5. It recomputes `missing_vectors` and `needs_reindex`. If a vector is still missing (the schema
   changed during the rebuild), the job ends `failed` with `error_type: rebuild_incomplete`: run it
   again. `needs_reindex` is cleared only when the embed space is unchanged since the last ingest. A
   rebuild never re-embeds content, so an embed-model change still needs a reingest. **Chunk-scope
   semantic fields:** a rebuild declares their vector but cannot fill it (content is copied as is and
   the backfill is document-scope). When no copied point carries such a field's vector, the job still
   ends `done` but `needs_reindex` stays `true` and the worker logs "reingest required for chunk-scope
   field(s) …" (the job result carries `reingest_required_fields`). Reingest the documents to fill it.
   A chunk-scope field no chunk has a value for is reported too; the reingest then clears the flag.

Generations and leftovers: before copying, the rebuild deletes every partial generation and every
generation superseded by the alias. The store the stable name resolves to is always the truth: if a
physical collection coexists with a stamped generation (a first swap whose delete failed), the stamped
copy is a stale leftover and is dropped, never adopted. A stamped generation is adopted only when the
stable name resolves to nothing at all (the first swap deleted the old store but could not create the
alias) — and then by every read and write path, not just the rebuild.
Leftover generations are not counted in the storage footprint until the next rebuild clears them.

Conflicts (`409`, body `{code, detail, …}`):

| `code` | When | Extra keys |
|---|---|---|
| `rebuild_index_active` | A rebuild is already pending or running on the collection | `job_id` |
| `collection_busy` | Other jobs (ingest, metadata sync…) are live on the collection | `job_ids` |
| `rebuild_unsupported_chunk_lexical` | The schema has a chunk-scope lexical field (legacy only: new ones are rejected with `422` at schema validation). The copy drops `meta_*_bm25` vectors and nothing refills chunk-scope ones, so the rebuild is refused | `fields` |

While a rebuild is pending or running, `POST /documents` (upload),
`POST /documents/{document_id}/reingest`, `POST /collections/{id}/reingest` and
`POST /collections/{id}/documents/reingest` answer `409 rebuild_index_active`. A bulk reingest also
answers `409 rebuild_index_required` (extra key `missing_vectors`) while the index lacks a named vector
the schema needs: a reingest cannot add one, so run the rebuild first. `404` when the collection is
unknown; `503` when the job could not be queued (the job row is then marked failed).

Cancelling a rebuild: `POST /jobs/{job_id}/cancel` (cooperative) stops it before the swap — the job
checks between copy batches and right before swapping; a cancel that arrives after that last check
is too late, and the rebuild completes (`done`, with the cancel logged). With
`force=true`, a **running** rebuild whose worker is alive (fresh heartbeat within
`WORKER_ALIVE_THRESHOLD_SECONDS`) is refused with `409 rebuild_force_cancel_refused` (extra key
`job_id`): forcing the row terminal would lift the ingest lock while the copy continues, and ingests
admitted then would land in the store the swap deletes. On a dead worker the force is allowed.

`DELETE /collections/{id}` answers `409 rebuild_index_active` while a rebuild is **running** (a queued
one is cancelled with the collection's other pending jobs).

Deleting a collection resolves the alias to its physical collection and deletes that collection,
which removes the alias too, plus any generation left over by an interrupted rebuild.

### Collection health

`GET /api/v1/collections/{collection_id}/health` — capability `read_technical`. An on-demand operational probe
of one collection: it builds **both** graphs (ingest + search), sweeps every provider-hosted node for
reachability, and reads the index size. **Zero spend** — nothing is enqueued and no provider work is
paid for (probes only).

The response is a `CollectionHealthResponse`:

| Field | Meaning |
|---|---|
| `verdict` | The roll-up: `operational` \| `empty` \| `degraded` \| `ingest_unavailable` \| `down` |
| `reason` | A jargon-free one-liner explaining the verdict (the banner text) |
| `checked_at` | When the probe ran (server time, UTC) |
| `ingest` | `{buildable, build_error, providers[]}` for the ingest graph |
| `search` | `{buildable, search_operational, build_error, providers[], index}` for the search graph |

`empty` is **neutral**, not a fault — the graphs build and providers answer, nothing is indexed yet.
`ingest_unavailable` means new documents cannot be ingested while the existing index stays
searchable; `down` means search itself cannot be served. `search.search_operational` is tri-state —
`true`, `false`, or `"degraded"` (embedder reachable but the index is empty, or a configured reranker
is unreachable). `search.index` carries `{vector_count, last_ingest_at}`.

Each entry of `ingest.providers` / `search.providers` is a probe result:
`{node_id, kind, family, side, status, endpoint, detail, latency_ms}`. `endpoint` is the probed base
URL and is always **secret-free** (never the api_key); it is `null` when nothing was probed. With the
egress allowlist enabled (`PROVIDER_EGRESS_ALLOWLIST`), a non-listed host is reported `blocked`
without being contacted.

```bash
curl -s http://localhost:10040/api/v1/collections/7f1c9d2e-.../health
```

`404` when the collection is unknown.

### Storage footprint

`GET /api/v1/collections/{collection_id}/storage` — capability `read_technical`. Measures how much hardware a
collection occupies, per store, plus a per-document breakdown sorted heaviest-first (so it doubles as
a top-N). Computed with grouped SQL aggregates and one Qdrant profile — no per-document N+1, no
cache.

| Field | Meaning |
|---|---|
| `s3` | **Exact** bytes: `{original_bytes, rendered_bytes, total_bytes, physical_unique_bytes, estimated:false}` |
| `postgres` | **Estimated** row bytes per bucket (documents / ir_blocks / enrichment / chunks / metadata / observability) + `total_bytes` |
| `qdrant` | **Estimated** `{points, dense_bytes, sparse_bytes, payload_bytes, total_bytes}` |
| `trace_bytes` | **Exact** bytes of the heavy full execution-trace payloads stored in S3 under `trace/{job_id}/` (a separate top-level S3 line, reclaimable via the trace-payload purge) — collection level and per document |
| `grand_total_bytes` | S3 `physical_unique_bytes` + Postgres + Qdrant + `trace_bytes` |
| `documents[]` | Per-document `{document_id, filename, s3, postgres, qdrant, trace_bytes, total_bytes}` |

Only S3 is exact (it reads the content-addressed blob registry, and `physical_unique_bytes` accounts
for dedup). Postgres bytes come from `pg_column_size` and exclude index/TOAST/bloat; Qdrant bytes are
count-based arithmetic and exclude index overhead. Every footprint carries an `estimated` flag saying
which it is — the numbers are never presented as measured when they are not. `trace_bytes` is summed
from a byte total recorded on each `job` row when its trace payloads are stored, so ONLY trace
captured after this shipped is counted (older payloads read as 0 until re-stored) — and it converges
back to 0 when the trace-payload purge reclaims those bytes.

`404` when the collection is unknown.

---

## 4. Documents & ingestion

Upload is the backend's only write into the pipeline. It content-addresses the file, dedups,
stores the original blob, admits `document + job + declared metadata` in one transaction, and
enqueues the ingestion job. Ingestion is **asynchronous** — poll the returned job (§7).

### Upload

`POST /api/v1/documents` — `multipart/form-data`, capability `write`.

| Form field | Required | Meaning |
|---|---|---|
| `file` | yes | The document bytes. |
| `collection_id` | yes | Target collection UUID. |
| `metadata` | no | JSON object `{field: value}` of declared metadata (default `"{}"`). |

```bash
curl -sX POST http://localhost:10040/api/v1/documents \
  -F "file=@/path/to/contract.pdf" \
  -F "collection_id=7f1c9d2e-4b8a-4c2f-9e3a-1a2b3c4d5e6f" \
  -F 'metadata={"client":"ACME","year":2026}'
```

Response (`202`):

```json
{ "document_id": "d4c3...", "job_id": "9a8b...", "duplicate": false }
```

- On an exact **duplicate** (same content + same pipeline config in this collection), the
  existing document is returned with `job_id: ""` and `duplicate: true` — nothing is re-run.
- `404` when the collection is unknown; `422` for a stale-unmigratable pipeline blob, invalid
  `metadata` JSON, or an unknown metadata field name. Types/required-ness are validated inside
  the pipeline (surfaced via the job's error), not at admission.
- `409 rebuild_index_active` while the collection's index is being rebuilt; `409
  rebuild_index_required` (extra keys `missing_vectors`, `missing_fields`) when the schema has a
  **chunk-scope** semantic/lexical field whose named vector the index does not declare — every chunk
  point would carry it, so the run is refused BEFORE any job is minted (no parse/LLM/embed spend).
  Run `POST /api/v1/collections/{id}/rebuild-index` first. A collection without chunk-scope
  searchable fields is never checked against the vector store.

### Re-ingest a document

`POST /api/v1/documents/{document_id}/reingest` — capability `write`. Re-runs the pipeline on a
document that is **already stored**, instead of delete-and-re-upload (re-uploading the same bytes is
refused as a duplicate). The worker refetches the original by its content hash and re-processes it
with the collection's **current** pipeline, so this is how you apply a config change to existing
documents.

| Query param | Type | Default | Meaning |
|---|---|---|---|
| `force` | bool | `false` | Bypass the stage cache and recompute every stage from scratch. Use after a code change that did not bump a node's cache version. |
| `replay_from` | string | — | Replay only this post-IR stage and its downstream on the document's **persisted** IR — no re-parse, no re-upload. One of `enrich`, `chunk`, `metagen_chunk`, `metagen_document`, `embed` as the pipeline allows (`contextualize` is never replayable — the raw chunker text it reads is not persisted; replay from `chunk`). A failed replay fails the job but keeps the document's prior status (plus a `warning_reason`): its previous chunks and vectors stay served. Only the downstream layers (enrichments / chunks / generated metadata / vectors) are replaced; blocks, pages and blobs stay. |

```bash
curl -sX POST "http://localhost:10040/api/v1/documents/d4c3.../reingest?force=true"
# a new metagen prompt, without re-parsing:
curl -sX POST "http://localhost:10040/api/v1/documents/d4c3.../reingest?replay_from=metagen_document"
```

`replay_from` errors (`422`, before any job is minted): `{"code": "replay_unsupported", "reason": …,
"allowed": [<stages this pipeline can replay from>]}` — an unknown/pre-IR stage, a stage not enabled in
the pipeline, or one whose upstream artefact is never persisted; a document with no persisted IR
(never fully ingested) is the same code with `allowed: []` — run a full reingest first. The job records
it as `JobStatus.replay_from` and its trace has no intake/parse node.

Response is an `UploadAccepted` (`202`) — `{document_id, job_id, duplicate}` — poll the job (§7). The
run is idempotent: the previous chunks/IR/pages are purged and the vectors overwritten, while the
user-declared metadata survives.

- `404` when the document is unknown.
- `409 rebuild_index_required` (same body as on upload) when a chunk-scope semantic/lexical field's
  named vector is missing from the index — refused before any job is minted; `409
  rebuild_index_active` while the index is being rebuilt.
- `409` when the document already has a queued/running ingestion job (two concurrent runs would
  interleave their Qdrant delete-and-upsert and strand orphan points). Wait for it or cancel it.
- `503` when the queue is unreachable — the freshly-minted job is marked `failed` rather than left
  orphaned as `pending`.

### Enable / disable a document

Reversible searchability toggle (no re-ingest) — a single Postgres flag that excludes the
document's chunks from retrieval.

`PATCH /api/v1/documents/{document_id}/enabled` — capability `write`.

```bash
curl -sX PATCH http://localhost:10040/api/v1/documents/d4c3.../enabled \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

Response: `{"document_id": "d4c3...", "enabled": false}`. `404` when unknown.

### Edit document metadata

Correct a document's metadata **values** in place — no re-ingest, chunk content untouched.

`PATCH /api/v1/documents/{document_id}/metadata` — capability `write`.

The new values are validated against the collection's schema, written to Postgres, and the
**filterable** Qdrant payloads are repainted synchronously (instant, no embed). When a changed field
feeds a named vector (`semantic` or `lexical`), a lightweight worker job is enqueued to re-embed
**only** the short metadata values onto the document's points (never the chunk content); the index
signature is unchanged, so this never triggers a reindex.

Accepts **document-scope** `user` and `generated` fields (a `generated` override is overwritten
again on the next reingest/metagen, which rewrites that set). Rejects, with `422`:

- an **unknown** field name,
- a **chunk-scope** field (its value lives per chunk — a reindex is required, there is no cheap
  value-edit path),
- a value whose shape does not match its field type,
- a `null` on a **required** field (a required field cannot be unset).

A `null` value on a **non-required** field **clears** it: the stored row is deleted and its
denormalised Qdrant footprint (the filterable payload key and/or the `semantic`/`lexical` named
vectors) is removed synchronously — clearing needs no embedding, so it never enqueues a job.

```bash
curl -sX PATCH http://localhost:10040/api/v1/documents/d4c3.../metadata \
  -H "Content-Type: application/json" \
  -d '{"values": {"topic": "ai-safety", "abstract": "a short summary"}}'
```

Response (`MetadataUpdateResponse`):

```json
{
  "updated_fields": ["abstract", "topic"],
  "reembedding": true,
  "reembed_fields": ["abstract"],
  "job_id": "a1b2c3..."
}
```

`reembedding`/`job_id` are only set when a changed field is `semantic`/`lexical` (`job_id` is the
re-embed job; otherwise `null`). `values` must carry at least one field. `404` when the document is
unknown.

### Chunk toggles

Also `write`. Toggle one or many chunks' searchability (no re-embed):

| Method | Path | Body |
|---|---|---|
| `PATCH` | `/api/v1/chunks/{chunk_id}/enabled` | `{"enabled": bool}` |
| `PATCH` | `/api/v1/chunks/enabled` | `{"chunk_ids": [...], "enabled": bool}` |

The single-chunk response carries `reindex_required: true` when you enable a chunk that was
never embedded (it has no Qdrant point until a later on-demand embed). The bulk response returns
per-chunk `results` plus a `not_found` list (unknown ids are skipped, not an error).

---

## 5. Explorer (browse ingested documents)

Read surface over a collection's documents. Every document-keyed route enforces the caller's
collection scope; an unknown id is `404`.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `GET` | `/api/v1/collections/{collection_id}/documents` | `read_text` | Document catalogue (newest first) |
| `GET` | `/api/v1/documents/{document_id}` | `read_text` | Full facts + resolved doc-level metadata |
| `GET` | `/api/v1/documents/{document_id}/pages` | `read_technical` | Pages, in order (geometry + render blob ref) |
| `GET` | `/api/v1/documents/{document_id}/ir` | `read_technical` | The full canonical IR (large) |
| `GET` | `/api/v1/documents/{document_id}/provenance` | `read_technical` | Ingestion provenance — the parser/model pipeline (per-stage trace) that produced the IR + chunks |
| `GET` | `/api/v1/documents/{document_id}/chunks` | `read_text` | Chunks (enriched text, block ids, metadata) — optionally paginated (`limit`/`offset`) and lean (`include_geometry=false`; forced lean for a key without `read_technical`) |
| `GET` | `/api/v1/documents/{document_id}/markdown` | `read_text` | Markdown view, generated on the fly from the IR (`?pages=` for a page range) |
| `GET` | `/api/v1/documents/{document_id}/html` | `read_text` | HTML view, generated on the fly from the IR (`?pages=` for a page range) |
| `GET` | `/api/v1/documents/{document_id}/outline` | `read_text` | Heading outline (`DocumentOutline`) — level, text, 1-based page, section-opening chunk |
| `GET` | `/api/v1/chunks/{chunk_id}/context` | `read_text` | A chunk + its enabled neighbours by `chunk_index` (`ChunkContext`) |
| `DELETE` | `/api/v1/documents/{document_id}` | `write` | Delete everywhere (`204`) |
| `POST` | `/api/v1/documents/{document_id}/trace-payloads/purge` | `write` | Reclaim a single document's stored full execution-trace payloads (`TracePurgeResult`) |

```bash
# List a collection's documents
curl -s http://localhost:10040/api/v1/collections/7f1c9d2e-.../documents

# One document's detail
curl -s http://localhost:10040/api/v1/documents/d4c3...
```

A `DocumentListItem` carries `id, filename, format, status` (`pending`/`processing`/`done`/
`failed`), `page_count`, `file_size`, `created_at`, `title`, `language`, `enabled`, `chunk_count`
(chunks persisted at ingestion — `0` = empty, `null` = unknown/legacy), and `warning_reason` (a
non-fatal warning on a `done` document — e.g. a run that completed but produced `0` chunks; `null`
when none). A `0`-chunk run resolves to `done`-with-`warning_reason`, never `failed`.

`DocumentDetail` adds `collection_id`, `mime_type`, `source_kind`, `source_hash`,
`pdf_blob_hash`, `simhash`, `pipeline_version`, and a `metadata` array of resolved
`{field_name, value, origin}` values (it also carries the same `chunk_count` and
`warning_reason`). It further carries `failure_reason` (the failing job's error message on a
`failed`/`cancelled` document — why it did not ingest; `null` when it did not fail; its URLs,
`host:port` pairs and request paths are masked as `<redacted>` for a key without `read_technical`) and
`searchable` (a computed boolean — `true` only when the document is `enabled` AND fully ingested
AND not known-empty; a `failed` or `0`-chunk document is never `searchable`, regardless of the
`enabled` toggle, which reflects only the user's intent).

`ChunkInfo` carries `id, chunk_index, text, token_count, is_indexed, role, enabled, strategy,
parent_id, block_ids[], metadata[]`. Pages (`PageInfo`) reference a `render_blob_hash` you fetch
via §8.

**Chunk listing paging + lean mode.** `GET /documents/{id}/chunks` takes optional query params —
defaults reproduce the historical full listing:

| Query param | Type | Default | Meaning |
|---|---|---|---|
| `limit` | int `1..500` | none (every chunk) | Page size, in `chunk_index` order |
| `offset` | int `>= 0` | `0` | Chunks to skip |
| `include_geometry` | bool | `true` | `false` drops `block_ids` and the 0-based `page` from each item (keys absent, `page_number` kept) — the agent-sized shape |

The response stays a JSON array; the document's total chunk count is in the **`X-Total-Count`**
response header (always set — and listed in CORS `Access-Control-Expose-Headers`, so a cross-origin
browser client can read it, like `X-Request-ID`, `Idempotency-Replayed`, `Retry-After` and
`Content-Disposition`). `422` on an out-of-bounds `limit`/`offset`.

### Reading a document piecemeal (outline + chunk context)

`GET /api/v1/documents/{document_id}/outline` — capability `read_text`, scoped by the document's
collection; `404` unknown. Returns `DocumentOutline{document_id, display_title, page_count,
headings[]}`, built from the IR heading blocks in reading order. Each heading is
`{level, text, page_number, chunk_id}`: `page_number` is 1-based (`null` on a page-less document);
`chunk_id` is the chunk covering the heading's position — the first chunk (in `chunk_index` order)
whose last block sits at or after the heading in reading order. Linking is structural, never by
heading text, so a title repeated under two chapters links to its own section; `null` for a heading
after the last chunk. No body text — cheap even on a very large document.

`GET /api/v1/chunks/{chunk_id}/context?before=1&after=1` — capability `read_text`, scoped by the chunk's
collection; `404` unknown chunk; `before`/`after` are `0..5` (default `1`, `422` outside).
Returns `ChunkContext{document_id, display_title, chunks[]}`: the target plus up to `before`
preceding and `after` following chunks of the same document, in `chunk_index` order. Disabled
neighbours (non-body roles, user-hidden chunks) are skipped — the window reaches past them
(chunk-level state only: a disabled document's chunks still read as neighbours); the target is
always included (`is_target: true`) whatever its state; a document edge simply yields fewer
neighbours. Items are lean: `{chunk_id, chunk_index, text, page_number, heading_path, token_count,
is_target}` (no geometry, no metadata).

```bash
curl -s http://localhost:10040/api/v1/documents/d4c3.../outline
curl -s "http://localhost:10040/api/v1/chunks/8a1f.../context?before=2&after=2"
```

**Page numbering.** `page` / `PageInfo.page_number` are **0-based indexes** (legacy, kept for
backward compatibility). The reader's page number is **1-based** and additive: `page_number` on
`ChunkInfo`, on each `IRBlock`, and on search hits/`block_locations`; `page_label` on `PageInfo`
(named differently there because `PageInfo.page_number` predates it with the 0-based meaning).
Cite the 1-based value. **Titles**: `DocumentListItem`, grid rows and `DocumentDetail` carry
`display_title` (the collection's `title_field` value when set and present, else the parsed title);
`title` stays the raw parsed title.

> The IR payload (`/ir`) is the whole canonical document (blocks, tables, figures, enrichments)
> and can be large — fetch it deliberately.

### Document views (markdown / HTML)

`GET /api/v1/documents/{document_id}/markdown` and `GET /api/v1/documents/{document_id}/html` —
capability `read_text`. Both render the document's **canonical IR** into a view format on the fly (the
IR is canonical; markdown/HTML are always generated, never stored sources — §"Non-negotiables").

| Query param | Type | Default | Meaning |
|---|---|---|---|
| `download` | bool | `false` | Truthy → `Content-Disposition: attachment; filename="<stem>.md"` (or `.html`). Falsy → inline (renders in a browser tab). |
| `pages` | string | none (whole document) | Render only these **1-based** pages: `5`, `5-7`, `5,7-9` (ascending, de-duplicated). In markdown each page is preceded by a marker line `<!-- page N -->`; in HTML each page is a `<section data-page="N">` inside the one standalone UTF-8 HTML5 document. An empty page keeps its marker. `422` (message names the page count) on bad syntax, page `0`, a reversed range, a page beyond `page_count`, or any selector on a page-less document. |

```bash
# Inline in a browser
curl -s http://localhost:10040/api/v1/documents/d4c3.../markdown

# Force a download with the right filename
curl -s "http://localhost:10040/api/v1/documents/d4c3.../html?download=true" -O -J

# Only pages 5 to 7 (each behind a <!-- page N --> marker)
curl -s "http://localhost:10040/api/v1/documents/d4c3.../markdown?pages=5-7"
```

Responses are `text/markdown` and `text/html` respectively. `404` when the document is unknown,
`403` when it belongs to a collection outside the caller's scope, `422` on a malformed document
UUID or `pages` selector.

### The document grid & bulk operations

The catalogue route above is the simple newest-first listing. At 10k–100k+ documents you want the
**grid**: a filtered, sorted, paginated query plus bulk actions that take the *same* target model, so
"select all 5 000 matching, deselect 3, act on the rest" never enumerates ids client-side.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/documents/query` | `read_text` | `DocumentQueryResponse` — one page + the total match count |
| `POST` | `/api/v1/collections/{collection_id}/documents/delete` | `write` | `BulkDeleteResponse` — delete everywhere (Postgres + Qdrant + orphan blobs) |
| `POST` | `/api/v1/collections/{collection_id}/documents/set-enabled` | `write` | `BulkEnabledResponse` — bulk searchability toggle |
| `POST` | `/api/v1/collections/{collection_id}/documents/reingest` | `write` | `BulkReingestResponse` — bulk full re-run (`202`) |

All four fail fast in the same order: collection exists (`404`) → caller is scoped to it (`403`) →
the request is structurally valid (`422`) — **before** any mutation or spend.

**Query** takes `{filter, sort, pagination}` (all optional):

- `filter` — AND-combined clauses over base columns (`filename`/`title` as `{contains, eq}`;
  `status`, `format`, `language` as membership lists; `file_size`, `page_count` as `{gte, lte}`;
  `created_at` as a datetime `{gte, lte}`; `enabled` as an exact bool) plus `metadata`, a list of
  `{field, op, value}` predicates against the collection's own metadata fields (`op` is one of `eq`,
  `contains`, `in`, `gte`, `lte`). An **empty** filter matches the whole collection.
- `sort` — `{field, direction}`; `field` is a base column or a metadata field name. The server always
  appends `id` as a secondary key so offset paging never skips or duplicates a row.
- **Title = display title.** When the collection has a `title_field`, the `title.contains` filter and
  the `title` sort run on the row's `display_title` (that field's value — a list joined with `", "` —
  falling back to the parsed title when unset/blank), not the raw parsed `title`. Without a
  `title_field` they run on the parsed title, as before. A filter-mode `DocumentSelector` (bulk ops)
  applies the same rule, so a bulk op selects exactly what the grid showed.
- `pagination` — `{limit, offset}`; `limit` is clamped down to `CORPUS_MAX_PAGE_SIZE`.

Every model is `extra="forbid"`: a typo in a filter key is a `422`, never a silently dropped
predicate. An unknown/non-filterable metadata field, a mismatched operator or an unknown sort field
is also `422`.

```bash
curl -sX POST http://localhost:10040/api/v1/collections/$CID/documents/query \
  -H 'Content-Type: application/json' \
  -d '{
        "filter": {"status": ["failed"], "metadata": [{"field": "client", "op": "eq", "value": "ACME"}]},
        "sort": {"field": "created_at", "direction": "desc"},
        "pagination": {"limit": 50, "offset": 0}
      }'
```

The response is `{total, limit, offset, rows}`; each row is a `DocumentListItem` plus a compact
`metadata` map of `{field_name: value}` (bulk-loaded per page, never N+1). Read the *schema* of those
metadata columns from `GET /api/v1/collections/{id}`.

**The three bulk routes take a `DocumentSelector`** — an explicit id list **XOR** a filter:

```json
{ "document_ids": ["d4c3...", "a1b2..."] }
```
```json
{ "filter": {"status": ["failed"]}, "exclude_ids": ["d4c3..."] }
```

Exactly one mode is allowed (`422` otherwise); `document_ids` must be non-empty, and `exclude_ids`
(the deselected few) is only meaningful in filter mode. An empty `filter` means the whole collection.

- **delete** → `{collection_id, matched, deleted, capped, max_selection}`. A filter matching more than
  `CORPUS_MAX_DELETE_SELECTION` deletes only the first N in a deterministic order and reports
  `capped: true` — never a silent truncation. Delete is convergent: re-run the same selector to remove
  the remainder.
- **set-enabled** → `?enabled=<bool>` is a **query** param. Returns
  `{collection_id, enabled, matched, updated, reindex_implied}`; `updated` excludes rows already in
  the target state, and `reindex_implied` is always `false` (a document toggle is a Postgres flag, not
  a re-index).
- **reingest** → `?force=<bool>` as on the single-document route. The stored pipeline is healed and
  structurally validated **once** before any job is minted (`422`), so a broken collection surfaces
  here instead of as N failed jobs. Returns `{collection_id, matched, enqueued, capped, max_fanout,
  skipped_in_flight, jobs}` (`202`) with one job handle per run; a match beyond
  `CORPUS_MAX_REINGEST_FANOUT` enqueues only the first N and reports `capped: true` with the full
  `matched`. `skipped_in_flight` counts documents skipped because an ingestion job was already active
  for them (at most one active run per document is a hard invariant), so `enqueued + skipped_in_flight`
  can be below the kept count when some targets were already running. `?replay_from=<stage>` replays
  every target from that stage (same contract and `422 replay_unsupported` as the single-document
  route); targets with no persisted IR are skipped and counted in `skipped_not_replayable`.
- **Bulk reingest guardrails** (this route AND `POST /collections/{id}/reingest`, whose JSON body takes
  the same `replay_from` / `confirm_estimate` fields):
  - **`409 estimate_required`** — more than `CORPUS_REINGEST_CONFIRM_THRESHOLD` resolved documents
    (default 200, `0` = off) without `confirm_estimate=true` (`?confirm_estimate=true` here, body field
    on the collection route). Detail: `{code, message, matched, threshold, estimate}` where `estimate` =
    `{document_count, total_cost_usd, total_cost_lower_bound_usd, cost_complete}` over the SAME targets
    — plus `total_prompt_tokens, total_completion_tokens, priced_stages, caveats` (which name models,
    providers and rate keys) ONLY for a caller holding `read_technical` (with `replay_from`, only
    the stages from it onward are priced; `null` if the estimator failed). Review it, resend with
    `confirm_estimate=true`. Nothing is minted on refusal.
  - **`429 queue_saturated`** + `Retry-After: QUEUE_RETRY_AFTER_SECONDS` — the arq backlog plus this
    call's jobs (kept targets minus those already running) would exceed `QUEUE_MAX_DEPTH`. Detail:
    `{code, message, queue_depth, requested, max_depth}`. Checked before any job is minted. A single
    upload/reingest is never gated.

---

## 6. Search

Hybrid retrieval over one collection. Runs **inline** in the request (sub-second, no queue).

`POST /api/v1/collections/{collection_id}/search` — capability `search`.

### SearchRequest

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | string | — | Natural-language query (non-blank). Embedded with the collection's own embedder. |
| `limit` | int (1–100) | `10` | Number of fused results. |
| `filters` | object/null | `null` | Constraints on **filterable** fields, ANDed across fields — see **Filter grammar** below. |
| `search_in` | list/null | `null` | Fields × modalities to query. `null` → content on both semantic + lexical. |
| `return_fields` | list/null | `null` | Lean hits: keep only these hit fields (any hit field name, or `metadata.<field>` for one metadata entry). `chunk_id` + `document_id` are **always** returned. Omitted fields are **absent** (not `null`) and their hydration reads are skipped. `null` → the full hit. Unknown name → `422` listing the allowed names. |
| `group_by` | `"document"`/null | `null` | `"document"` → no document contributes more than `max_per_document` hits (see below). |
| `max_per_document` | int (1–10) | `1` | Per-document cap under `group_by`; sending it without `group_by` → `422`. |
| `min_score` | float/null | `null` | Drop hits whose **final** `score` is below this, after ranking (and before grouping). The scale depends on `score_kind` — a fusion score is rank-based, a cross-encoder rerank score is in [0, 1] — so set it against the scores you observe. **Scale change (release note):** a single-branch retrieval (one dense-only target) now reports the raw cosine (`score_kind: raw_dense`, around 0.6) instead of an RRF score (around 0.016), so a stored `min_score` tuned on the RRF scale now keeps almost everything — re-tune it. |
| `rerank` | bool/null | `null` | Per-request override of the collection's rerank stage: `false` skips reranking for this request (fusion order); `true` requires it (`422` when the collection's search pipeline has no rerank stage); `null` → the pipeline as configured. |
| `fusion` | `"rrf"`/`"dbsf"`/null | `null` | Per-request override of the hybrid fusion strategy (reflected in `score_kind`). |
| `debug` | bool | `false` | `true` → each hit also carries `fusion_score` (its retrieval fusion score) and, when a reranker re-scored it, `rerank_score`. |

**Filter grammar** (`filters` on search and on chunk browse):

- `{"field": "v"}` — equality; string/enum/keyword_list values match **case-insensitively**.
- `{"field": ["a", "b"]}` — any-of (keyword_list: overlap); max 100 values, never empty.
- Operator form `{"field": {"<op>": value}}` — **one** operator per field (only range bounds combine):
  - `"eq": v` / `"in": [..]` — same as the bare forms.
  - `"not": v` / `"not_in": [..]` — exclude; string values exclude every stored case variant.
  - `"contains": "sub"` / `"prefix": "pre"` — string/enum/keyword_list: case-insensitive match against
    the **stored** values (more than 500 matching values → `422`, narrow it; none → empty result + a
    hint). On text/text_list fields `"contains"` is the full-text match; `"prefix"` is not allowed.
  - `"exists": true|false` — the field has a value / is absent, null or empty.
  - `"gte"`/`"gt"`/`"lte"`/`"lt"` — range on integer/float/datetime fields only (datetime bounds are
    ISO-8601 strings, e.g. `{"published": {"gte": "2024-01-01", "lte": "2024-12-31"}}`).
- Allowed operators by type: string/enum/keyword_list `eq,in,not,not_in,contains,prefix,exists` ·
  text/text_list `eq,in,not,not_in,contains,exists` · integer `eq,in,not,not_in,exists` + ranges ·
  float/datetime `exists` + ranges · bool `eq,not,exists`. Anything else → `422` listing the valid ones.
- Operator operands must have the field's value type (integer field → integers, bool → `true`/`false`,
  string/text → strings): a mistyped value → `422` (a mistyped `not` would otherwise exclude nothing).
- text/text_list fields: `{"field": "words"}` is a full-text match (all words present); a list = any-of.
- A value no document stores returns a `hint` with the closest stored values.

Each `search_in` entry is a **SearchTarget**: `{ "field": "content"|<metadata field>,
"semantic": bool, "lexical": bool }`. `field` defaults to `"content"` (the chunk body).
A **lexical metadata** target is real BM25 on collections created since 0.28 (accent-folded, French +
English stopwords and stemming, IDF over the collection); an older collection keeps its previous
sparse encoding until it is rebuilt. When the targets resolve to **one single vector** (e.g. one
metadata field, lexical only), no fusion runs: each hit's `score` is that vector's raw score (BM25 /
sparse dot / cosine) rather than a rank-based fusion score, and `score_kind` says so (`raw_dense` /
`raw_sparse`) — a `min_score` then cuts on that raw scale. When **every** target is a metadata field, the rerank stage is skipped
(the cross-encoder scores the chunk body, irrelevant to a field match) unless `rerank: true` is sent.

**Grouping** (`group_by: "document"`): the graph is asked for a deeper page
(`limit × max(3, 2 × max_per_document)`, capped at 200), then the **final** ranking — after fusion and
any rerank — is walked in order, admitting a hit only while its document is under the cap, until
`limit` hits. When that deeper page holds too few distinct documents, **fewer** than `limit` hits come
back (never more than the cap per document); `debug_info.grouping.fetched` reports the page size read.
With a rerank stage the deeper page also enlarges the reranked pool.

Gates (all `422`, before any spend): a list filter that is empty (`[]` matches nothing — omit the
filter instead) or carries more than 100 values; a filter naming a non-filterable field; an enum
value outside the field's declared values; an unknown operator, an operator not valid for the field's
type, or two operators combined (other than range bounds); a `contains`/`prefix` matching more than
500 stored values; a `search_in` target naming a vector
the collection never indexed (or a selection with no modality). A field flagged semantic/lexical
whose named vector the vector store has not declared yet is also rejected:
`field 'X' has no indexed <semantic|lexical> vector — … rebuild_index …`. Before this gate, Qdrant
rejected the query and the route answered with the misleading "stored search graph is invalid". `404` when the collection is
unknown; `409` when it has no embed node wired.

Runtime failures are surfaced as typed errors (each carries a machine-readable `{code, detail}`):

| Status | `code` | Meaning |
|---|---|---|
| `504` | `search_timeout` | The search run blew its wall-clock cap. |
| `424` | `embedder_unreachable` | The query embedder is a dead host / transport / drifted blob. |
| `424` | `embedder_auth_failed` | The embedder endpoint rejected the credentials. |
| `503` | `embedder_overloaded` | The embedder still answered its probe — the failure was transient; retry. |

### SearchResponse

```json
{
  "query": "termination clause",
  "hits": [
    {
      "chunk_id": "c1...",
      "document_id": "d4c3...",
      "filename": "msa-acme-2025.pdf",
      "document_title": "Master Services Agreement",
      "heading_path": ["Article 7 — Termination"],
      "metadata": {"client": "ACME", "year": 2025},
      "score": 0.0731,
      "text": "Either party may terminate ...",
      "chunk_index": 12,
      "token_count": 148,
      "block_ids": ["b41", "b42"],
      "page": 6,
      "page_number": 7,
      "bbox": [0.12, 0.34, 0.88, 0.41],
      "block_locations": [
        {"page": 6, "page_number": 7, "bbox": [0.12, 0.34, 0.88, 0.41]}
      ]
    }
  ],
  "score_kind": "rrf_fusion",
  "debug_info": null,
  "hints": []
}
```

A hit self-cites so a UI needs no follow-up `GET /documents/{id}`: `filename` and `document_title`
(the human identity — `document_title` is `null` when no title was parsed/generated), `heading_path`
(the chunk's section ancestry, top-down; empty under no section), and `metadata` (the document's
filterable fields). `block_ids` are the IR blocks the chunk was assembled from; `page` + `bbox`
locate the chunk's primary (leading) block and `block_locations` gives every source block's
`{page, bbox}` — all bboxes are `[x0, y0, x1, y1]` **normalised to [0, 1]** (multiply by the page
image size to draw), and `page`/`bbox` are `null` (and `block_locations` empty) for an unlocated
chunk (e.g. a page-less document). `score` is the hit's score (higher is better; the fused RRF
score by default). `score_kind` (always present) names what the score represents — `rrf_fusion`
(the default), `dbsf_fusion`, `cross_encoder_rerank` (when a reranker scored the hits; it wins over
the others), `raw_dense` (one dense vector queried, no fusion — a cosine similarity, e.g. a
`dense_only` collection) or `raw_sparse` (one sparse vector — its raw sparse dot / BM25 score,
unbounded). A fusion score is rank-based, comparable only **within** one response — a round `1.0000` on a tiny/single-doc corpus is normal, not a bug. `debug_info` always
carries `hit_count`, plus non-fatal notes when they apply (e.g. `degraded`, `grouping`). With
`debug: true` each hit also carries `fusion_score` and, when reranked, `rerank_score` (both absent
otherwise).

`page` is the **0-based** index; `page_number` (on the hit and on each `block_locations` entry) is the
same page **1-based**, as a reader counts it — cite that one (`null` when unlocated).

**`hints`** (always present, `[]` when none): when a filter value matches no stored value of its field
(even ignoring case) — or a filtered search returned no hits — the (still `200`) response carries
`[{field, value, message, suggestions[]}]`, where `suggestions` are the closest stored values to retry
with, best first. An agent should read them before concluding nothing exists.
A **stopword-only query** (no searchable term after stopword/punctuation removal) against a metadata
**lexical** target whose vector is BM25-encoded queries nothing; the empty answer then carries one hint
per such target — `field` = the target, `value` = the query, message `query has no searchable term for
lexical target '<field>' (only stopwords or punctuation) … add a content word or use semantic`. It is
emitted only for that cause.

### Example

```bash
curl -sX POST http://localhost:10040/api/v1/collections/7f1c9d2e-.../search \
  -H "Content-Type: application/json" \
  -d '{
        "query": "termination clause",
        "limit": 5,
        "filters": {"client": "ACME", "year": [2025, 2026]},
        "search_in": [
          {"field": "content", "semantic": true, "lexical": true},
          {"field": "summary", "semantic": true}
        ]
      }'
```

### Browse chunks (no query)

`POST /api/v1/collections/{collection_id}/chunks/browse` — capability `read_text`, collection-scoped. Lists
a collection's **enabled** chunks matching filters, with no query text: read a whole document ("all
passages of P0153") or a business process page by page. Ordered by document then `chunk_index`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `filters` | object/null | `null` | Same grammar, gates and `hints` as search filters. `null` → every chunk. |
| `limit` | int (1–200) | `20` | Page size. |
| `cursor` | string/null | `null` | The `next_cursor` of the previous page (opaque; an unknown value → `422`). |
| `return_fields` | list/null | `null` | Same projection as search (`chunk_id`/`document_id` always returned). |

Response: `{chunks: [hit-shaped items without a score], next_cursor: string|null, hints: [...]}` —
`next_cursor` is `null` on the last page. Searching with a blank `query` stays `422`, and its message
points here.

### Search health

`GET /api/v1/search/health` — capability `read_technical`.

A compact, tile-friendly roll-up of search-runtime health for the deployment **Overview** cockpit.
Because search runs **inline** (no job/fleet surface of its own), this mirrors the operational tiles
`GET /api/v1/jobs/queue` and `GET /api/v1/jobs/workers/live` power. Every figure is **cumulative since
process start**, read straight off the in-process `docforge_search_*` Prometheus series (the same
source Grafana scrapes — no parallel counters); it is a **process-global aggregate** carrying no
per-tenant data or ids. Trends/rates over time stay in Grafana; this is the at-a-glance snapshot.

**SearchHealthSummary**:

| Field | Type | Meaning |
|---|---|---|
| `total_runs` | int | Total search runs since process start (router `4xx` rejections are not counted). |
| `error_rate` | float | Failed/timeout/unavailable runs over total, in `[0, 1]` (`0.0` when `total_runs == 0`). |
| `p95_latency_ms` | float/null | 95th-percentile whole-run latency in ms (bucket-based approximation); `null` when no run recorded. |
| `zero_result_rate` | float | Zero-result runs over total, in `[0, 1]` (`0.0` when `total_runs == 0`). |
| `avg_hits` | float/null | Mean delivered hits per successful search; `null` when none observed. |

```json
{
  "total_runs": 1284,
  "error_rate": 0.012,
  "p95_latency_ms": 420.0,
  "zero_result_rate": 0.081,
  "avg_hits": 7.4
}
```

---

## 7. Jobs

Ingestion status, plus a cancel control. The worker writes the rows; the API serves them (and can
request a cancellation).

| Method | Path | Cap | Returns |
|---|---|---|---|
| `GET` | `/api/v1/jobs` | `read_text` | Jobs — a collection's (`?collection_id=`) or fleet-wide, filterable — a paginated `JobPage` |
| `GET` | `/api/v1/jobs/{job_id}` | `read_text` | One job's live state (poll this) |
| `GET` | `/api/v1/jobs/{job_id}/events` | `read_technical` | Per-node execution trace, in order (each event carries its score + shape summaries + `has_full_*` flags) |
| `GET` | `/api/v1/jobs/{job_id}/events/{event_id}/payload?slot=input\|output` | `read_technical` | One node's FULL raw input/output payload (opt-in `full` trace tier), fetched on demand (`JobEventPayload`); `404` when only a shape summary exists |
| `GET` | `/api/v1/jobs/{job_id}/stream` | `read_technical` | Live progress as Server-Sent Events (see below) |
| `GET` | `/api/v1/jobs/workers/live` | `read_technical` | What every worker is doing right now |
| `GET` | `/api/v1/jobs/queue` | `read_technical` | Backlog depth — `{pending, running}` |
| `GET` | `/api/v1/jobs/cost?collection_id={id}` | `read_technical` | A collection's paid text-gen roll-up (`CollectionCost`) |
| `GET` | `/api/v1/jobs/stage-durations?collection_id={id}` | `read_technical` | Average per-stage wall-clock — the ETA basis (`StageDurations`) |
| `GET` | `/api/v1/jobs/failures/breakdown` | `read_technical` | Failure aggregation over a window — top causes / by stage / by collection (`FailureBreakdown`) |
| `GET` | `/api/v1/jobs/failures/new?since={ts}` | `read_technical` | "X new failures since a cursor" signal — count + optional ids (`NewFailures`) |
| `GET` | `/api/v1/jobs/timeseries` | `read_technical` | Lightweight hourly job trends — done/failed/arrivals/backlog sparklines (`JobTimeseries`) |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | `write` | Request cancellation of a queued/running job (`CancelResult`) |

> `document_id` is `null` on a collection-level job (`kind: rebuild_index`, see "Rebuild the index"
> in §3); every other job kind carries its document.
>
> `collection_id` is **optional** on `GET /api/v1/jobs`. **Present** → scoped to that collection (and
> it scopes the key). **Omitted** → a **fleet-wide** listing across every collection (the "All Jobs"
> view), which is **full-access only**: a collection-scoped key must name a collection it owns, else
> `403` — the same gate `GET /api/v1/jobs/queue` applies to its fleet-wide counts. A **pending** job
> has `worker_id: null` (arq assigns the worker at claim time — never fabricated).

`GET /api/v1/jobs` is **paginated + filterable + sortable** — the "All Jobs" triage view (a collection
— or the fleet — can hold thousands of job rows). Query params:
- `collection_id` (optional) — scope to one collection, or omit for fleet-wide (see the note above).
- `status` (optional, **repeatable**) — filter to one or more of `pending`/`running`/`done`/`failed`/
  `cancelled` (e.g. `?status=pending&status=running`). Omit for all statuses.
- `stage` (optional) — filter to jobs in this stage (the node's `current_stage`). Omit for all stages.
- `error_type` (optional) — filter to jobs with this structured failure class (e.g. `TimeoutError`,
  `worker_killed`, `job_timeout_exceeded`). Omit for all.
- `search` (optional) — case-insensitive **prefix** match on the job id **or** document id (paste a
  full id or a leading fragment). Omit for no id search.
- `created_after` / `created_before` (optional) — ISO-8601 instants bounding the creation-date range.
- `sort` (optional) — the sort dimension: `created` (default), `duration` (wall-clock run time — a
  still-running job by elapsed time, a queued one sorts last) or `status`.
- `order` (optional) — the sort **direction** applied to `sort`: `newest` (default = DESC — newest /
  longest / z-a, the monitoring view) or `oldest` (ASC — **FIFO / "what runs next"** for `created`,
  typically paired with `status=pending`; shortest-first for `duration`; a-z for `status`).
- `limit` (optional) — page size, clamped down to the server's `JOBS_MAX_PAGE_SIZE` (its default).
- `offset` (optional) — rows to skip for paging.

The response is a `JobPage` — `{ total, limit, offset, jobs }` where `total` is the full match count
(drives the pager), `limit`/`offset` echo the applied values, and `jobs` is the page in the requested
order (newest first by default).

A `JobStatus` carries `job_id, document_id, collection_id, status` (`queued`/`running`/`done`/
`failed`/`cancelled`), `kind` (`ingest` — a full pipeline run — or `metadata_sync` — a lightweight
per-document metadata re-embed following an in-place value edit), `replay_from` (the stage an ingest
job replays from on the persisted IR; `null` for a full run), `progress` (0–100), `current_stage`,
`error` (only when failed — verbatim for a `read_technical` key, its URLs/`host:port`/paths masked as `<redacted>` otherwise),
`attempt`, `started_at`, `finished_at`, and `updated_at` (last progress write — freezes on a wedge).
It also joins display labels (`document_filename`, `document_title`, `collection_name`, each `null`
if the row is gone) plus `display_title` — the document's display title resolved exactly like the
document list/grid (the collection's `title_field` value when set, else the parsed title; `null` when
neither exists, the document is gone, or on the SSE stream) — a `cancel_requested` flag and a `stalled` flag (a RUNNING job idle past the
stall threshold — an early wedge warning), the paid-generation roll-up (`total_prompt_tokens`,
`total_completion_tokens`, `cost_usd`), `duration_seconds` (wall-clock run time — `finished_at −
started_at` for a terminal job, elapsed time for a running one, `null` while queued), the live fan-out
counter (`items_done`/`items_total`, `null` outside a fan-out stage), and — only on a failed job — a
failure breadcrumb (`failed_node_id`, `failed_node_kind`, `failed_item_index`, `error_type`).

### Poll an ingestion to completion

```bash
JOB=9a8b...
while :; do
  STATE=$(curl -s http://localhost:10040/api/v1/jobs/$JOB | jq -r .status)
  echo "$STATE"
  [ "$STATE" = "done" ] || [ "$STATE" = "failed" ] && break
  sleep 2
done
```

On `failed`, read `error` on the job (or `GET /api/v1/jobs/{id}/events` for the per-node trace —
each `JobEvent` has `stage, status` (`success`/`failed`/`skipped`), timestamps, `detail`). The trace
is the FULL execution tree: alongside root stages it now carries every nested node (group children,
per-item ForEach body instances). Each `JobEvent` additionally exposes `score` (a scored node's
`[0, 1]` quality, `null` otherwise), `node_path` (materialized path — root = bare id, nested =
`enrich.figures[3].vlm`), `depth` (`0` = root stage), `parent_path`, and `item_index` (ForEach item
index, `null` outside a fan-out). The list stays FLAT and pre-order (parent before its children,
ForEach items by ascending index); a client rebuilds the tree from `node_path`/`depth`. Legacy rows
predating this leave the five fields `null`.

`GET /api/v1/jobs/workers/live` returns running jobs grouped by worker (empty when idle). Each
`WorkerActivity` carries its liveness (`alive`, `busy`, `last_seen`, `started_at`) plus `max_jobs`
— the worker's configured parallel-job capacity (arq concurrency, = `WORKER_CONCURRENCY`). `max_jobs`
is `null` for a worker whose build predates this field (or a pre-column heartbeat row); a UI pairs it
with the count of `jobs` as a "N running / max" capacity chip and never fabricates a number when null.
Each `WorkerActivity` also carries live resource samples taken (via psutil) at its last heartbeat:
`cpu_percent` (recent CPU utilisation percent — may exceed 100 on a multi-core host), `mem_mb`
(resident memory in megabytes) and `mem_percent` (resident memory as a percent of host RAM). All three
are `null` when not reported — an old heartbeat row, a worker on a build that does not sample resources,
the first (unprimed) tick, or a psutil error — and a UI must render them as "unknown" rather than 0.

### Live progress (Server-Sent Events)

`GET /api/v1/jobs/{job_id}/stream` — capability `read_technical`. Prefer this over polling `GET /jobs/{id}` for
a live UI. The job is resolved and scope-checked **before** the stream opens, so an unknown id is a
normal `404` and never an error buried mid-stream.

The response is `text/event-stream`; each frame is `data: {...}\n\n` carrying a `frame` type (the
dedicated envelope key — a `status` frame's `JobStatus` payload carries its own `kind`, so the envelope
never reuses `kind`):

- `frame: "event"` — one newly-landed stage event (the same shape as a `JobEvent`), in execution order.
- `frame: "status"` — the full `JobStatus` snapshot, emitted only when it actually changes (so progress
  flows through without a per-tick spam of identical frames). A `{"frame": "status", "status": "gone"}`
  frame means the job row was deleted mid-stream.

The feed is DB-poll-backed (no message bus): it re-reads the job row and its stage-event table every
`SSE_POLL_INTERVAL_SECONDS` and emits only the delta. It closes as soon as the job reaches a terminal
state (`done`/`failed`/`cancelled`), always after a final status frame.

```bash
curl -sN http://localhost:10040/api/v1/jobs/9a8b.../stream
```

### Telemetry

`GET /api/v1/jobs/queue` — the backlog: `{pending, running}` (queued-but-unclaimed vs executing).
Fleet-wide counts are **full-access only**; a collection-scoped key must pass `?collection_id=` (a
query-less call from a scoped key is `403`, so single-tenant keys can never read cross-tenant totals).

`GET /api/v1/jobs/cost` — requires `collection_id` as a query param. Returns a `CollectionCost`:
`{collection_id, total_prompt_tokens, total_completion_tokens, cost_usd, document_count}`, the
**post-hoc** roll-up of what the collection's jobs actually spent (the pre-hoc projection is §11).

`GET /api/v1/jobs/stage-durations` — requires `collection_id` as a query param. Returns
`{collection_id, stage_seconds}`, a stage id → average wall-clock seconds map computed over the
collection's `done` jobs. A UI sums the not-yet-completed stages of a running job to estimate its
remaining time.

Both `cost` and `stage-durations` carry the collection in the **query string**, so the caller's
collection scope is enforced on that value.

### SRE observability — aggregation & trends (no Prometheus)

These three endpoints give the UI what it needs to **aggregate** and **track over time** without the
optional Prometheus/Grafana add-on — everything is derived in SQL from the `job` table. Each takes an
optional `collection_id` and is gated exactly like `GET /jobs`: a named collection is scoped to the
key, an omitted one is a **fleet-wide** read restricted to full-access keys.

`GET /api/v1/jobs/failures/breakdown` — the "why is it breaking" panel. `window_hours` (default `24`,
max `720`) sets the look-back; FAILED jobs **created** in that window are rolled up three ways, each
ordered by descending count and bounded to the dominant causes. Returns a `FailureBreakdown`:
`{ collection_id, window_hours, since, total_failed, by_error_type[], by_stage[], by_collection[] }`.
`by_error_type`/`by_stage` are `{ label, count }` (a null group key surfaces as `"unknown"`);
`by_collection` is `{ collection_id, collection_name, count }`.

`GET /api/v1/jobs/failures/new?since={ts}` — the "X new failures since you last looked" signal. The
client passes its last-seen cursor (`since`, ISO-8601); the count is keyed on the **failure instant**
(`finished_at`), so a job created before the cursor but failing after it still counts. `include_ids`
(default `false`) also returns the bounded id list (`limit`, default `50`, max `500`). Returns a
`NewFailures`: `{ since, count, job_ids[], latest_failed_at }` — pass `latest_failed_at` as the next
`since` to advance the cursor without double-counting.

`GET /api/v1/jobs/timeseries` — lightweight in-product sparklines. `window_hours` (default `24`, max
`168`) of **contiguous hourly buckets**, computed from the job rows: arrivals (`created`), successful
completions (`done`), failures (`failed`) and a reconstructed end-of-hour `backlog` (queued + running).
Returns a `JobTimeseries`: `{ collection_id, window_hours, bucket_seconds, buckets[] }` where each
`TimeseriesBucket` is `{ bucket_start, created, done, failed, backlog }`, oldest first.

---

## 8. Blobs

`GET /api/v1/blobs/{content_hash}` — capability `read_technical`. Streams a content-addressed blob's raw
bytes with its **registered** media type (never a guessed one): page renders and figure crops
(load as `<img src>`), the canonical PDF, or the original upload.

```bash
curl -s http://localhost:10040/api/v1/blobs/2f1a9c... --output page-3.png
```

`404` when the hash is unknown. A blob has no single owner: a **scoped** key may reach it only
through a collection it owns (an orphan/foreign blob → `403`). A full-access key skips that
check. When auth is on, send the bearer as with any `/api/v1` route.

---

## 9. Pipelines (design surface — advanced)

The pipeline endpoints power the graph/stage design UI. The blob shapes are large and opaque
(a serialized node graph); treat them as produced by these endpoints, round-tripped, and stored
on a collection's `pipeline`/`search`. All require `read_technical`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/pipelines` | Discover surfaces — one entry per pipeline (`ingest`, `search`) with its URLs |
| `GET` | `/api/v1/pipelines/{key}` | Lean design payload: palette + default blob + `presets` + issues (`?full=true` for advanced blocks) |
| `POST` | `/api/v1/pipelines/{key}/inspect` | Build + validate + describe a posted blob |
| `POST` | `/api/v1/pipelines/{key}/edit` | Apply graph operations server-side, then inspect the result |
| `POST` | `/api/v1/pipelines/{key}/stages/view` | Stage view of a blob + validity (ingest-only) |
| `POST` | `/api/v1/pipelines/{key}/stages/apply` | Compile a stage action into the blob + view (ingest-only) |
| `POST` | `/api/v1/collections/{collection_id}/pipeline/stages/apply` | Apply ONE stage action to a collection's STORED pipeline and persist it (`write` + `read_technical`, collection-scoped) |

`{key}` is `ingest` or `search`. An unknown key is `404`. The stage endpoints are **ingest-only**
today — an unknown OR non-stage pipeline key `404`s, and the discovery index omits the stage URLs
for pipelines with no stage rail.

The lean design payload also carries `presets` — the curated creation presets this pipeline offers
(`[{name, label, description, is_default}]`). Their `name` is what a client passes as the create
request's `preset` (ingest) / `search_preset` (search). Ingest offers `standard` (default), `light`,
`ocr_scan`, `high_precision`; search offers `hybrid` (default), `hybrid_rerank`, `dense_only`.

Design philosophy: a malformed/invalid blob is returned as **data** (`valid: false` + `issues`,
or `build_error`/`edit_error`), never as an HTTP error — the editor renders the problems in place.

**`set_config` `mode`** — `"replace"` (default, unchanged behaviour: the `config` dict IS the node's
new config) or `"merge"` (`{**current, **config}`; a `null` value deletes that key so it falls back to
its default — except on a secret field, where `null` **clears** it, i.e. stores `""`). Use `merge` for
single-key edits — every other key is kept; a merge that changes `base_url` drops every secret it does
not restate (re-send `api_key` with the new `base_url`).

**Secrets on write** — on every blob write (collection `PATCH` pipeline/search, snippet apply, the
collection-scoped stage apply below) a secret field (`api_key`/`password`) that is **masked or omitted**
keeps the stored key of the **same provider at the same endpoint**: same node id, family AND kind (for a
chain step, the same kind at that position, or a same-kind step at the same explicit `base_url` after a
reorder) whose normalised **effective** endpoint is unchanged — effective = the explicit `base_url`, else
the node Config's default, so an omitted and an explicit default URL are the same endpoint; scheme, host,
port and path are normalised, trailing slash ignored. A kind mismatch never restores (a mask is then
blanked). **An endpoint change never carries a stored key**: a masked/omitted secret whose provider's
`base_url` changed is refused with **422** (`"… api_key must be re-entered because its endpoint
(base_url) differs …"`) — re-send the secret, or `""` to clear it. **Nested secrets** follow the same
rule: a secret-named key anywhere inside a node config (e.g. a metagen `targets[*].api_key`) is masked on
every read/export surface and restored only from the stored item with the same `field` AND the same
effective endpoint (its own `base_url`, else the node's) — a target whose endpoint changed must re-send
its key. **A nested endpoint override never borrows its parent's key**: a metagen target with its own
`base_url`, or a structgen step (`gen_*`) whose `base_url` matches none of the metagen node's keyed
endpoints, that OMITS its `api_key` is refused with 422 (`"node 'meta_doc_prep' targets[summary].api_key
must be re-entered …"`) — send its own key, or `""` to call it keyless. The runtime enforces the same rule
on already-stored blobs: an override inherits the parent key only when its `base_url` is empty or
normalises to the parent's endpoint, otherwise it sends its own key (possibly none). A key is bound to
the `base_url` declared next to it: an override with an EMPTY `base_url` calls the parent's endpoint with
the parent's key and its own `api_key` is ignored, so moving the parent never drags an override key along. A stateless `/stages/apply` chain
rebuild marks such a step's secret with the redaction mask plus a `notices` entry, so the follow-up
write is refused the same way. Only an explicit `""` (or `null` in merge mode) clears a key. Build /
validation errors (`build_error`, 422 details) never echo config input values, so no secret is
reflected in a response or a log line.

**Collection-scoped stage apply** — `POST /api/v1/collections/{collection_id}/pipeline/stages/apply`
(`write`), body `{"action": <StageAction>, "note": null}`. The server heals the collection's stored
pipeline, applies the action, resolves secrets as above, validates, and — when the result is valid AND
differs from the stored one — persists it through the same write as a `PATCH` (a new `config_version`
row, `needs_reindex` re-derived). Response `CollectionStageApplyResponse`: `collection_id`, `persisted`,
`needs_reindex`, `stages` (the stage view, secrets **masked**), `valid`, `issues`, `notices`,
`build_error`. An invalid result or a no-op is `200` with `persisted: false` and a notice — nothing is
written. `404` unknown collection, `403` outside the key's scope, `422` unmigratable stored pipeline.
The read → compile → write is a compare-and-swap on the config version: if another write (a `PATCH`, a
snippet import, another stage apply) lands in between, the action is recomputed once on the new stored
pipeline; if it loses again the call is `409` and nothing is overwritten — re-read and retry.

```bash
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/pipeline/stages/apply \
  -H 'Content-Type: application/json' \
  -d '{"action": {"action": "set_config", "stage": "embed", "mode": "merge", "config": {"timeout_seconds": 30}}}'
```

`?full=true` fills the advanced `palette.mechanics` block, which is self-describing: alongside
`conditions`/`binding_sources`/`containers`/`error_policies` it now carries `edit_operations` (every
`/edit` `operations[]` variant) and `stage_actions` (every `/stages/apply` `action` variant), each a
card with its discriminator `kind` + a `params_schema` derived from the model — so a client composes
those payloads without guessing. `stage_actions` is empty for a pipeline with no stage rail (search).

```bash
# Discover surfaces
curl -s http://localhost:10040/api/v1/pipelines

# Open the ingest design surface (palette + default blob)
curl -s http://localhost:10040/api/v1/pipelines/ingest
```

---

## 10. Config snippets (granular export/import)

Where a `.dcexport` bundle (§"Transfers" in the MCP/SDK docs) moves a **whole** collection
(schema, config, and data) asynchronously across servers, a **snippet** moves **just one config
facet** — synchronously, config-only, no documents/vectors involved. Useful to copy a tuned
pipeline graph or search config from one collection to another, or to version a schema
independently of the data it describes.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collections/{collection_id}/snippets/{kind}` | `read_technical` | Export one config facet as a `CollectionSnippet` |
| `POST` | `/api/v1/collections/{collection_id}/snippets/{kind}` | `write` | Apply a `CollectionSnippet` onto this collection |

`{kind}` is one of `pipeline`, `search`, `schema`.

### Export

```bash
curl -s http://localhost:10040/api/v1/collections/$CID/snippets/pipeline
```

Returns a `CollectionSnippet`:

```json
{
  "kind": "pipeline",
  "format_version": 1,
  "docforge_version": "0.9.0",
  "body": { "nodes": [ "..." ] }
}
```

- `kind` — echoes the requested facet.
- `format_version` — the snippet schema version (bumped only on a breaking snippet-shape change).
- `docforge_version` — the exporting server's product version, checked on import.
- `body` — for `pipeline`/`search`, the graph blob with any provider secrets **masked** (never
  exported in the clear); for `schema`, `{"fields": [...]}` (the `fields[]` array, §3).

Save the response as a `*.dfsnippet` file — deliberately a distinct extension from `.dcexport`,
so the two artifact kinds are never confused.

### Import

```bash
curl -sX POST http://localhost:10040/api/v1/collections/$CID/snippets/pipeline \
  -H 'Content-Type: application/json' \
  --data @tuned-pipeline.dfsnippet
```

Body is a `CollectionSnippet` (as produced by export). Response is a `SnippetImportResult`:

```json
{ "collection_id": "7f1c9d2e-...", "kind": "pipeline", "needs_reindex": false }
```

`needs_reindex` mirrors the collection-level flag (§3) — `true` when applying the snippet altered
the searchable surface.

Because provider secrets are masked at export, a `pipeline`/`search` snippet exported from one
collection and applied to **another** arrives with masked secrets: **re-enter any base URL/API key
placeholders** the imported graph references before it can run (mirrors the stored-blob-staleness
auto-heal path — a masked secret is not a valid one).

`404` when the collection is unknown. `422` on `format_version`/`kind` mismatch, or an invalid
graph/schema body (the same structural checks as a direct `PATCH` to the collection, §3).

---


## 10b. Config history (versions, diff, restore)

Every pipeline/search config write — collection creation (v1), a `PATCH` carrying `pipeline`/`search`,
a collection-scoped stage apply, a pipeline/search snippet apply, and a restore — appends an
immutable **config version** stamped with its **author**: `<key name> (<key prefix>)` (e.g.
`root (df_3f9a…)` for the root token — the prefix makes the label unforgeable; key names `root` and
`anonymous` are reserved and refused at key create/rotate with `422`), `anonymous` when auth is disabled, or `null` for history written before authorship was
recorded / system writes (import). The metadata schema is not versioned here.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collections/{collection_id}/config-versions` | `read_technical` | Newest-first page (`limit` 1–200, default 50; `offset`) |
| `GET` | `/api/v1/collections/{collection_id}/config-versions/diff?from=&to=` | `read_technical` | Structured diff between two versions |
| `GET` | `/api/v1/collections/{collection_id}/config-versions/{version}` | `read_technical` | One version's `{pipeline, search}` snapshot |
| `POST` | `/api/v1/collections/{collection_id}/config-versions/{version}/restore` | `write` | Re-apply a version as a NEW version |

- **List** → `ConfigVersionListResponse` `{collection_id, total, limit, offset, items[]}`; each item
  `{version, created_at, note, author_label, author_key_id, changes}` where `changes` names what
  differs from the previous version: `pipeline:<node id>`, `pipeline:(graph)` (transitions/bindings)
  or `search` (empty for v1).
- **Get** → `ConfigVersionDetail` (the summary + `config`); every provider secret is **masked**.
- **Diff** → `ConfigVersionDiffResponse` `{from_version, to_version, changes[]}`; each change is
  `{path, op: added|removed|changed, before, after}` with JSON-pointer paths where graph nodes are
  keyed by id (`/pipeline/nodes/parse/config/max_pages`). Values are always masked: a rotated key
  shows as a `changed` entry with both sides masked.
- **Restore** → `ConfigVersionRestoreResponse` `{restored_from, version, needs_reindex}`; writes a new
  version noted `restore of v{N}` through the same locked write as a `PATCH` (fail-fast structural
  validation → `422`; a concurrent config write → `409`). **Secret rule:** the stored snapshot holds
  real keys, but a provider still present at the **same endpoint** keeps its **current** key (a key
  rotated since is never rolled back); a provider whose current key lives at a **different endpoint**
  is refused with `422` (re-enter the key with a `PATCH`); a provider with no current key gets the
  snapshot's **own** key back (same endpoint it was stored with — nothing is carried to a new host).

Unknown collection or version → `404`.

## 10c. Collection aliases

A **collection alias** is a stable, deployment-level name (`chatmop`) pointing at ONE collection.
Rebuild a collection alongside (`chatmop-v2`), then switch the alias in one atomic call: every client
addressing the alias and every key scoped `alias:chatmop` follow it, with no key or app edit.
(Unrelated to the vector-store aliases of §3 "Rebuild the index".)

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collection-aliases` | `read_text` | Every alias whose target the caller may see, by name |
| `PUT` | `/api/v1/collection-aliases/{name}` | `admin`, full-access key | Create (`201`), or atomically re-point (`200`) — the "switch" |
| `DELETE` | `/api/v1/collection-aliases/{name}` | `admin`, full-access key | Delete the alias (`204`); the collection is untouched |

- **Name** — a slug `^[a-z0-9][a-z0-9_-]{0,62}$`, not UUID-shaped, not `contract-schema`/`import`
  (`422` otherwise).
- **PUT body** `{"collection_id": "<uuid>"}` → `SetCollectionAliasResponse`
  `{name, collection_id, collection_name, created_at, updated_at, previous_collection_id, created}`.
  Unknown target → `404`.
- **Alias writes need a full-access (unscoped) admin key** (`403` for a collection-scoped key):
  re-pointing or re-creating an alias re-scopes every key bound to `alias:<name>`, including keys a
  scoped admin could never manage, so it is a root-grade act.
- **DELETE is refused (`409`) while live keys still name `alias:<name>`** — a freed name would
  silently re-bind those keys to whoever re-creates it. Re-scope or revoke them first, or re-point
  the alias instead.
- **Every collection-scoped route accepts the alias in place of the UUID**: the `{collection_id}`
  path param (`GET /api/v1/collections/chatmop/search`…), the `collection_id` query param of the
  `/jobs` routes, and the `collection_id` form field of `POST /api/v1/documents`. An unknown alias
  (or a ref that is neither a UUID nor a valid slug) → `404`. For a collection-scoped key an alias
  OUTSIDE its scope answers the same `404` (never a `403` naming the target id), and a key lacking
  the route's capability gets the same `403` whether the alias exists or not. `GET /collections/{id}` lists the
  `aliases` pointing at it.
- **Namespace collision → `409` both ways**: an alias may not equal a collection name, and a
  collection may not be created/renamed to an alias name (case-insensitive).
- **Deleting a collection an alias targets → `409`** — re-point or delete the alias first (the
  `ON DELETE RESTRICT` foreign key is the backstop).
- Every create / re-point / delete is recorded in the audit trail (§13) with target type
  `collection_alias` and the alias name as id.
- Aliases are **not** exported or imported (§12): they are a deployment-level naming concern, so a
  bundle imported elsewhere gets no alias.

## 11. Cost estimate (dry-run)

Before spending anything on ingestion, project the cost and volume of running a collection's
pipeline over its documents. This is a **pre-hoc estimate** — no job is enqueued, nothing is spent,
no writes happen. It reads the collection's **actual** pipeline config (only enabled cost-incurring
stages are costed) plus cheap per-document stats, then projects per-stage token/page usage and
dollar cost against the same rate model the post-hoc job meter uses.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/estimate` | `read_technical` | A `CostEstimate` — per-stage breakdown + totals |

The body is optional; when omitted, `scope` defaults to `pending`.

```json
{ "scope": "pending" }
```

- `scope` (`"pending"` \| `"all"`, default `"pending"`) — which documents to estimate over.
  `pending` covers uploaded-but-not-yet-ingested documents (the usual "what will this ingest cost?"
  preview); `all` covers every document in the collection (the cost of a full reingest).
- `document_ids` (`list[string]`/null) — estimate over exactly these document ids instead (e.g. the
  rows currently selected in the documents grid).
- `filter` (`DocumentFilter`/null) — estimate over a corpus slice, using the **same filter shape**
  as the documents-grid query (§5): status/format/metadata predicates rather than an explicit id
  list.

`document_ids` and `filter` are mutually exclusive (`422` if both are set). Whenever **either** is
given, `scope` is ignored — the estimate runs over exactly the selected rows or the filtered
corpus, not "pending"/"all". The response shape (`CostEstimate`) is identical across all three
modes.

```json
{ "document_ids": ["d4c3...", "a1b2..."] }
```

```json
{ "filter": { "status": ["failed"], "format": ["pdf"] } }
```

The response is a `CostEstimate`: a per-stage breakdown, the projected volume, the totals, plus the
**assumptions** it rests on (chunk sizing taken from the collection's chunker config, overridable
per collection — §3 "Estimate overrides") and any caveats. A stage whose model has no known rate is
reported with a **null cost** (its token/page volume is still shown) — never a fabricated number.
`total_cost_usd` is the full total only when every enabled paid stage is priced (`cost_complete:
true`); otherwise it is **null** and `total_cost_lower_bound_usd` carries the sum of the priced stages
(a minimum, always present — equal to the total when complete). Each unpriced stage adds a caveat
naming the model (or OCR provider), the stage and the override path to price it
(`estimate_overrides.rates.models.<model>` / `.embed.<model>` / `.ocr.<kind>`).

```bash
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/estimate \
  -H 'content-type: application/json' -d '{"scope":"all"}'

# Estimate over a specific selection
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/estimate \
  -H 'content-type: application/json' -d '{"document_ids":["d4c3...","a1b2..."]}'
```

`404` when the collection is unknown; `422` when its stored pipeline blob is unreadable (mirrors
the reingest error contract), or when both `document_ids` and `filter` are set.

---

## 11b. Pipeline preview (dry-run on one document)

See **exactly what the ingestion pipeline would produce on ONE document — without ingesting the
corpus and without persisting anything**. The ingest graph runs **inline** in the request (the same
pure engine a real run uses), then the delivery is projected into a bounded report; **no document
row, S3 object or Qdrant point is ever written**. This is the way to validate a pipeline change
before applying it to a whole collection.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/pipeline/preview` | `write` + `read_technical` | A `PreviewResponse` — IR summary + first N chunks + cost + trace |

The request is **`multipart/form-data`** (or form-urlencoded for the `document_id` path). Provide
**exactly one** source:

- `file` (upload) — the document bytes to dry-run; **or**
- `document_id` (form field) — an already-ingested document (its original bytes are re-read from the
  store, nothing is re-stored).

Optional form fields:

- `blob` — a candidate pipeline blob (JSON string) to preview **instead of** the collection's stored
  pipeline (try a pipeline edit before saving it).
- `metadata` — declared metadata (JSON object) for an uploaded source.
- `max_chunks` — how many chunks to include in the report (capped server-side by `PREVIEW_MAX_CHUNKS`).

**Interactive guardrails** (the run is synchronous): a short wall-clock cap
(`PREVIEW_RUN_TIMEOUT_SECONDS`) and a body-size cap (`PREVIEW_MAX_BYTES`). An oversized source is a
`422` — ingest it for the full pipeline instead.

The response is a `PreviewResponse`:

- `ok` — `true` when the run delivered a bundle; `false` when a node failed (the failure is **data**,
  not an error status — see `failed_node_id` / `error` / the `trace`).
- `ir` — a compact IR summary (title, language, page/block/figure counts, per-type block counts).
- `chunk_count` + `chunks` — the total produced and the first N (text truncated to
  `PREVIEW_CHUNK_TEXT_MAX_CHARS`, `chunks_truncated` flags the clip), each with role, heading path,
  token count, pages and any generated metadata.
- `vector_set_count` — how many chunk vector sets the embed stage produced.
- `cost` — the run's **actual** metered spend on this document (prompt/completion tokens, USD cost or
  null when unpriceable), priced against the collection's own rates.
- `trace` — the full per-node execution trace (materialized path, status, score, timing, errors).
- `warnings` — non-fatal notices (e.g. a clean run that produced 0 chunks).

```bash
# Dry-run an uploaded file against the collection's stored pipeline
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/pipeline/preview \
  -F 'file=@/path/to/report.pdf' -F 'max_chunks=5'

# Dry-run an already-ingested document with a candidate pipeline blob
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/pipeline/preview \
  -F "document_id=$DID" -F "blob=$(cat candidate_blob.json)"
```

`404` when the collection or the named document is unknown; `422` on a bad/unbuildable blob, a
missing/oversized source, or neither/both of `file` and `document_id`.

### Asynchronous worker-side preview (covers every pipeline)

The inline preview above runs in the **API process**, which does not carry the heavy parse
dependencies (docling) — so it cannot preview the default/docling pipelines. The **async** variant
enqueues a **worker** preview job that runs the full ingest graph with every dependency present (so
it covers ALL pipelines), still persisting **nothing**: the bounded report is returned as the job
result (kept in Redis with a TTL), never written to a table. Submit, then poll by the returned id.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/pipeline/preview/jobs` | `write` + `read_technical` | `PreviewJobAccepted` — `{preview_id, status}` (202) |
| `GET` | `/api/v1/collections/{collection_id}/pipeline/preview/jobs/{preview_id}` | `write` + `read_technical` | `PreviewJobResult` — `{preview_id, status, result, error}` |

The submit body is the **same `multipart/form-data`** as the inline preview (`file` XOR
`document_id`, optional `blob` / `metadata` / `max_chunks`). Uploaded bytes ride through the queue;
an existing `document_id` is re-read worker-side from the store. Guardrails are the worker knobs
`WORKER_PREVIEW_RUN_TIMEOUT_SECONDS` / `WORKER_PREVIEW_MAX_BYTES` / `WORKER_PREVIEW_MAX_CHUNKS`.

`PreviewJobResult.status` is `pending` (queued) / `running` / `done` (the `result` is a
`PreviewResponse`) / `failed` (the worker job itself crashed/timed out — distinct from a DATA
failure, which is `done` with `result.ok = false`). Polling an unknown or expired id is a `404`.

```bash
# Submit an async worker preview of an already-ingested document, then poll it
PID=$(curl -s -X POST http://localhost:10040/api/v1/collections/$CID/pipeline/preview/jobs \
  -F "document_id=$DID" | jq -r .preview_id)
curl -s http://localhost:10040/api/v1/collections/$CID/pipeline/preview/jobs/$PID | jq '.status, .result.chunk_count'
```

---

## 12. Collection transfers (portable `.dcexport` bundles)

Where a snippet (§10) moves one config facet, a **transfer** moves a **whole collection** — schema,
config, documents, IR, chunks and vectors — into a portable `.dcexport` bundle you can re-import on
another server with **no recompute** (ids are remapped on import, never preserved). Both directions
run **asynchronously**: the route returns `202` with a transfer handle you poll.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/export` | `read_technical` | Start packaging a collection into a bundle (`202`) |
| `POST` | `/api/v1/collections/import` | `create` | Import an uploaded bundle as a **new** collection (`202`) |
| `GET` | `/api/v1/transfers/{transfer_id}` | `read_technical` | Poll one transfer's live status |
| `GET` | `/api/v1/transfers/{transfer_id}/download` | `read_technical` | Stream a finished export's bundle bytes |

Export and import both return a `TransferAccepted` — `{transfer_id, kind, status}` where `kind` is
`export`/`import` and `status` is `pending`. The tracking row is created **before** the worker task is
enqueued, so the id is pollable the instant the call returns.

**Import** is `multipart/form-data`: `file` (the `.dcexport` bundle, required) and an optional
`target_name` for the new collection. The upload is streamed straight to staging without being
buffered in memory, so a multi-GB bundle imports with flat RAM. A **scoped** `create` key is
auto-granted ownership of the collection its import produces.

### Poll a transfer

`GET /api/v1/transfers/{transfer_id}` returns a `TransferStatus`:

| Field | Meaning |
|---|---|
| `transfer_id` / `kind` / `status` | The handle, the direction, and `pending`/`running`/`done`/`failed` |
| `progress` / `stage` | Coarse 0–100 percentage and the current engine stage label |
| `counts` | Per-table snapshot (`{"documents": n, "chunks": m, …}`) |
| `error` | The failure message, verbatim, when `failed` |
| `collection_id` / `collection_name` | Export → the source collection; import → the **new** collection once done |
| `size_bytes` / `format_version` / `dense_dim` | The produced bundle's facts (done export only) |
| `expires_at` | When a produced bundle may be garbage-collected |
| `started_at` / `finished_at` / `created_at` / `updated_at` | Lifecycle timestamps |

Scope follows the transfer's collection: an export is scoped to its source, a completed import to the
collection it produced. An import still in flight has no collection yet, so its unguessable transfer
id gates it until the produced id lands. `404` when the id is unknown.

### Download a bundle

`GET /api/v1/transfers/{transfer_id}/download` streams the bytes from object storage in bounded
chunks (never whole in memory) as `application/zstd`, with a `Content-Disposition` attachment
filename led by the collection name.

Only a **done export with a live bundle** is downloadable. Everything else — an unknown id, an
import, an unfinished or failed export, or an expired bundle — is a `404`; the collection scope is
enforced *before* those cases are distinguished, so a foreign key learns nothing about the transfer's
state.

```bash
TID=$(curl -sX POST http://localhost:10040/api/v1/collections/$CID/export | jq -r .transfer_id)
curl -s http://localhost:10040/api/v1/transfers/$TID | jq .status
curl -s http://localhost:10040/api/v1/transfers/$TID/download -O -J
```

Retention (`EXPORT_TTL_SECONDS`), staging lifetime and the reclaim crons are covered in
[configuration.md](configuration.md).

---

## 13. Audit trail

An append-only log of every **mutating** `/api/v1` request (`POST`/`PUT`/`PATCH`/`DELETE`). A
middleware records exactly one row per routed mutating request **after** the response is sent
(fail-safe — an audit write can never delay or fail the user's request); reads and non-API paths
are never audited. Each row captures the actor, the low-cardinality route **template** (not the
raw-id path), the final response status, the target resource (type + id parsed from the path), the
client IP, and the request's correlation id (see §15).

| Method | Path | Cap | Returns |
|---|---|---|---|
| `GET` | `/api/v1/audit` | `read_technical` + **full-access** | One newest-first, keyset-paginated page of the trail |

The trail spans **every tenant**, so it is restricted to a **full-access (root / unscoped) key** — a
collection-scoped key is rejected `403`, mirroring the fleet-wide job counts. Query params (all
optional filters):

| Param | Meaning |
|---|---|
| `limit` | Page size, clamped down to `AUDIT_MAX_PAGE_SIZE` (default `200`); defaults to that ceiling |
| `cursor` | Opaque keyset cursor from a previous page's `next_cursor` |
| `actor_user_id` | Filter to one acting user (UUID) |
| `actor_key_id` | Filter to one acting API key (UUID) |
| `target_type` | Filter to one target type (e.g. `collection`) |
| `target_id` | Filter to one target id (pair with `target_type`) |
| `correlation_id` | Filter to one request's correlation id (see §15) |
| `created_from` | Lower bound (**inclusive**) on `created_at` |
| `created_to` | Upper bound (**exclusive**) on `created_at` |

The response is an `AuditPage` — `entries`, the applied `limit`, and `next_cursor` (null once the
trail is exhausted). Page forward by feeding `next_cursor` back as `cursor`. A malformed cursor is a
`400`.

```bash
curl -s "http://localhost:10040/api/v1/audit?target_type=collection&limit=50" \
  -H "Authorization: Bearer $ROOT_TOKEN"
```

The trail is gated by `AUDIT_ENABLED` (default `true`); with it off, no rows are written.

---

## 14. Idempotency (`Idempotency-Key`)

Stripe-style safe retries on a small allow-list of mutating JSON endpoints. Send an
`Idempotency-Key: <your-key>` request header on an eligible request; the first call runs once and
its response is cached, and any **retry with the same key + same body** replays that stored response
verbatim instead of re-running the operation.

Idempotency is strictly **opt-in per request** (no header → normal behaviour) and engages **only**
on this explicit allow-list:

| Method | Route |
|---|---|
| `POST` | `/api/v1/collections` |
| `PATCH` | `/api/v1/collections/{collection_id}` |
| `POST` | `/api/v1/collections/{collection_id}/reingest` |
| `POST` | `/api/v1/collections/{collection_id}/documents/reingest` |
| `POST` | `/api/v1/collections/{collection_id}/export` |

Multipart uploads (document ingest, import-bundle upload) and the API-key create/rotate routes are
**deliberately excluded** — uploads are already content-addressed by sha256, and secret-returning
routes must never cache their one-time plaintext response body.

Behaviour:

- **Replay** — a completed key replayed with the **same body** returns the cached status + body,
  stamped with `Idempotency-Replayed: true`. A replay is *not* re-audited, but it still passes the
  auth + rate-limit gates (a retry still costs budget).
- **In progress** (`409`) — a second request arrives while the first with that key is still running.
- **Body mismatch** (`422`) — the same key is reused with a **different** request body (a client
  bug: the key was meant to identify one specific operation).
- **Scope** — a key is scoped to its actor (per API key, per user, or `anon` when auth is off), so
  one tenant's key never collides with another's.
- **TTL** — a cached record lives for `IDEMPOTENCY_TTL_HOURS` (default `24`), after which the key is
  forgotten and a GC cron prunes it.
- **Body cap** — a request body over `IDEMPOTENCY_MAX_BODY_BYTES` (default `262144` = 256 KiB) skips
  idempotency entirely (transparent passthrough).
- Only **definitive** (`< 500`) outcomes are cached; a `5xx`/exception drops the guard so a retry
  actually re-runs.

The whole feature is gated by `IDEMPOTENCY_ENABLED` (default `true`); with it off, the header is
ignored.

```bash
curl -s -X POST http://localhost:10040/api/v1/collections \
  -H 'content-type: application/json' \
  -H 'Idempotency-Key: 3f9c1a20-collection-create-001' \
  -d '{ ... collection contract ... }'
```

---

## 15. Request correlation (`X-Request-Id`)

Every response carries an `X-Request-Id` header — a per-request correlation id that also tags every
log line emitted while handling the request (so a response id maps straight to its logs in
Loki/loguru). This is always on and needs no configuration.

- **Propagation** — send an inbound `X-Request-Id` (or `X-Correlation-Id`) and it is honoured and
  echoed back unchanged, so an upstream proxy's id is preserved end-to-end. Omit it and the server
  mints one.
- **Coverage** — the id is stamped even on short-circuit `401`/`429` responses (the correlation
  middleware wraps auth + rate-limiting).
- **Client use** — log or surface the `X-Request-Id` from a response; quote it in a bug report to
  trace the exact request through the logs, or feed it to the audit trail's `correlation_id` filter
  (§13) to pull the audit row for that request.

```bash
curl -s -D - -o /dev/null http://localhost:10040/api/v1/collections | grep -i x-request-id
# X-Request-Id: 6b1f...   (echo an inbound one: -H 'X-Request-Id: my-trace-42')
```

---

## 16. Capabilities discovery

`GET /capabilities` is a **public** (`/health`-style, outside `/api/v1`, no auth) self-description of
what **this** deployment can actually do right now. It answers "which version am I, is auth on, is a
GPU present, which optional sidecars are up, and which pipeline kinds can I run now?" in one call —
so a client or UI can adapt without hardcoding the deployment's shape.

It never spends and never runs the engine: the pipeline kinds are read live from the node registry
palette, and each optional sidecar's reachability comes from a **short-cached** `GET /health` probe
(timeout `CAPABILITIES_PROBE_TIMEOUT_SECONDS`, memoised for `CAPABILITIES_CACHE_TTL_SECONDS`), so a
burst of calls costs at most one probe round per window.

```
GET /capabilities
```

```json
{
  "version": "1.2.3",
  "auth_enabled": false,
  "gpu_present": null,
  "services": [
    { "name": "bge_server", "role": "embed", "reachable": true, "device": null,
      "provides": ["embed:bge_server", "rerank:cross_encoder"], "detail": null },
    { "name": "mineru_server", "role": "parse", "reachable": false, "device": null,
      "provides": ["parser:mineru"], "detail": "unreachable" },
    { "name": "qdrant", "role": "vector", "reachable": true, "device": null,
      "provides": [], "detail": "declared (not probed)" }
  ],
  "capabilities": {
    "parsers": ["docling", "granite_docling"],
    "ocr": ["mistral", "rapidocr", "tesseract"],
    "embed": ["bge_server", "openai_compatible"],
    "chunkers": ["fixed_size", "semantic", "structure_aware"],
    "vlm": ["openai_compatible"],
    "llm": ["mistral", "openai_compatible"],
    "rerank": ["cross_encoder"],
    "contextualize": ["breadcrumb", "doc_meta", "llm", "sliding"],
    "metagen": []
  }
}
```

Field notes:

- `version` — the running app/image version (`FASTAPI_APP_VERSION`, falling back to `DOCFORGE_TAG`).
- `auth_enabled` — whether API-key bearer auth gates `/api/v1` here.
- `gpu_present` — `true` when any reachable sidecar reports device `"cuda"`, `false` when reachable
  sidecars report only non-cuda devices, `null` when no device information is available.
- `services[]` — the infra **stores** (reachability derived from config presence — declared, not
  live-probed) and the optional **sidecars** (reachability from the cached `/health` probe). `provides`
  lists the capability ids (`"family:kind"`) a service unlocks; empty for infra stores.
- `capabilities.<family>` — the **selectable** pipeline kinds available now: an in-worker or
  per-collection-key kind is always listed; a sidecar-gated kind (e.g. `parser:mineru`) appears only
  while its sidecar is reachable. `metagen` has no provider kind of its own (it delegates to `llm`),
  so it is legitimately empty.

---

## 17. Errors

FastAPI's standard error envelope is used throughout:

```json
{ "detail": "Collection 7f1c9d2e-... not found." }
```

Request-validation errors (`422`) carry FastAPI's structured `detail` array:

```json
{ "detail": [ { "loc": ["body", "query"], "msg": "query must not be blank", "type": "value_error" } ] }
```

Each error carries `type`, `loc`, `msg` (and `ctx` when pydantic provides one) — never the submitted
`input` value: FastAPI's default would echo it (for a missing field, the whole request body), so a
malformed request would reflect its own `api_key`, password or document text back.

`500` responses are opaque (`{"detail": "Internal server error"}`) unless the app runs in debug
mode (`FASTAPI_DEBUG_MODE`), which then includes the error/traceback/function — never in
production.

| Status | When |
|---|---|
| `400` / `422` | Validation failure — bad body, blank query, unknown metadata field, non-filterable filter, invalid search target, unmigratable/invalid pipeline blob, a config snippet with a version/kind mismatch or invalid graph/schema (§10), an estimate request with both `document_ids` and `filter` set (§11), or an `Idempotency-Key` reused with a different body (§14). |
| `401` | Auth on and the bearer is missing/invalid/revoked/expired (carries `WWW-Authenticate: Bearer`). |
| `403` | Authenticated but lacking the capability, not scoped to the target collection/resource, or a scoped key on the full-access audit trail (§13). |
| `404` | Unknown collection / document / chunk / job / blob / pipeline key. |
| `409` | Name clash (collection / key), rotating an already-revoked key, root not provisioned, a collection with no embed node on search, cancelling an already-terminal job (§7), re-ingesting a document that already has an active job (§4), or an `Idempotency-Key` whose request is still in progress (§14). |
| `424` | Search only — the query embedder is a permanent config fault: `embedder_unreachable` or `embedder_auth_failed` (typed `{code, detail}`, §6). |
| `503` | Search — `embedder_overloaded`: the embedder answered its probe, so the failure was transient; retry (§6). Ingestion — the queue was unreachable, so the freshly-minted job was marked failed (§4). |
| `504` | Search only — `search_timeout`: the run blew its wall-clock cap (§6). |
| `500` | Unexpected server error (opaque). |
