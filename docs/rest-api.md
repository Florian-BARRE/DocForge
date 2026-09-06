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
| Cost estimate (dry-run) | `/api/v1/collections/{collection_id}/estimate` | §11 |
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
  `read`, `write`, `search`, `create`, `admin`.
  Endpoints demand one of these (e.g. search requires `search`, upload requires `write`,
  creating a collection requires `create`, key management requires `admin`).
- **Collection scope** — either `["*"]` (every collection) or an explicit list of
  collection UUID strings. A scoped key is rejected `403` on any collection it does not list —
  including collections referenced in a form body, a query param, or via a document/chunk/blob.

Plus an optional **`expires_at`** (absolute instant; `null` = never expires).

A `permissions` of `null` means **full access** (the root shape) — it bypasses every capability
and scope check. `KeyPermissions` uses `extra="forbid"`; the `collections` wildcard `"*"` cannot
be mixed with explicit ids, and every explicit id must be a valid UUID.

| Capability | Grants |
|---|---|
| `read` | List/get collections, browse documents, read pages/IR/chunks, read blobs, read jobs |
| `write` | Patch/delete collections, upload documents, toggle enabled, delete documents/chunks |
| `search` | Run collection search |
| `create` | Create collections. A **scoped** key that creates one is auto-granted ownership — the new collection id is appended to the key's own `collections` scope, so it can then manage what it created (per its other capabilities) without knowing ids in advance |
| `admin` | Manage API keys (create/list/revoke/rotate) |

### 401 vs 403 semantics

- **401 Unauthorized** — no/invalid/revoked/expired bearer, or inactive owner. Carries
  `WWW-Authenticate: Bearer`. The failure detail is deliberately opaque (never reveals which
  check failed).
- **403 Forbidden** — the key authenticated fine but lacks the demanded capability, or is not
  scoped to the target collection, or has a malformed permissions blob.

### Key-management endpoints

All require the `admin` capability. Keys are owned by the sole `root` account.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/auth/keys` | Create a key — returns the plaintext **once** (`201`) |
| `GET` | `/api/v1/auth/keys` | List keys, newest first (metadata only) |
| `DELETE` | `/api/v1/auth/keys/{key_id}` | Soft-revoke a key (`204`, idempotent) |
| `POST` | `/api/v1/auth/keys/{key_id}/rotate` | Issue a fresh secret, revoke the old key (`201`) |

> The plaintext key is returned **only** at creation and rotation, in the `key` field. It is
> hashed at rest and can never be recovered — store it immediately.

**Create a scoped key** (read + search, limited to one collection):

```bash
curl -sX POST http://localhost:10040/api/v1/auth/keys \
  -H "Authorization: Bearer $ROOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "reporting-service",
        "permissions": {
          "capabilities": ["read", "search"],
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
  "permissions": { "capabilities": ["read", "search"], "collections": ["7f1c9d2e-..."] },
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
          "capabilities": ["read", "write", "search", "create"],
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
  "capabilities": ["read", "search"],
  "collections": ["7f1c9d2e-4b8a-4c2f-9e3a-1a2b3c4d5e6f"]
}
```

- `authenticated` — always `true` (an unauthenticated request never reaches this route).
- `root` — `true` for full, unscoped access: auth disabled, or a `null`-permissions key. Then
  `capabilities` lists every capability and `collections` is `["*"]`.
- `capabilities` / `collections` — exactly what the key was granted (§"The key model").

A key whose stored permissions blob is malformed is `403`, mirroring the authorization gate — never
a `500`.

---

## 3. Collections

A collection is the **contract**: a metadata schema + an ingestion pipeline blob + a search
config blob. The vector space is fixed at creation (named vectors cannot be added to Qdrant
later), so declare the **full** schema up front.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collections` | `read` | List all collections with their schema |
| `GET` | `/api/v1/collections/contract-schema` | `read` | JSON Schema of the identity/limits contract (drives the create form) |
| `GET` | `/api/v1/collections/{id}` | `read` | One collection's full contract |
| `POST` | `/api/v1/collections` | `create` | Create a collection (`201`); a scoped creator is auto-granted ownership of it |
| `PATCH` | `/api/v1/collections/{id}` | `write` | Patch identity/limits/schema/config |
| `DELETE` | `/api/v1/collections/{id}` | `write` | Delete a collection (`204`) |
| `GET` | `/api/v1/collections/{id}/health` | `read` | Zero-spend provider preflight sweep + an overall verdict |
| `GET` | `/api/v1/collections/{id}/storage` | `read` | Material footprint across all three stores (exact S3, estimated PG/Qdrant) |
| `POST` | `/api/v1/collections/{id}/reingest` | `write` | Re-run the full pipeline over the whole collection (`202`) |

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

`needs_reindex` (read-only, on the response) flips `true` when a config/schema change alters the
searchable surface and the collection must be reindexed.

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

`GET /api/v1/collections/contract-schema` — capability `read`. Returns the **JSON Schema** of the
collection identity/limits contract (`name`, `supported_formats`, `max_file_size_bytes`,
`job_timeout_seconds`, `preset`) — the same model `POST /api/v1/collections` composes, so the two can
never drift. A UI feeds it straight to a schema-driven form and a new scalar contract field surfaces
with no client change.

```json
{ "config_schema": { "title": "CollectionContractModel", "type": "object", "properties": { "...": {} } } }
```

The metadata schema (`fields[]`) is **not** part of this document — it is described in "The metadata
FieldSpec" above.

### Create a collection

```bash
curl -sX POST http://localhost:10040/api/v1/collections \
  -H "Content-Type: application/json" \
  -d '{
        "name": "contracts",
        "supported_formats": ["pdf", "docx"],
        "max_file_size_bytes": 52428800,
        "fields": [
          {"field_name": "client", "field_type": "string", "required": true, "filterable": true},
          {"field_name": "year", "field_type": "integer", "filterable": true},
          {"field_name": "summary", "field_type": "text", "origin": "generated", "semantic": true}
        ]
      }'
```

Returns the created `CollectionModel` (`201`). `409` on a name clash, `422` on a bad pipeline or
colliding vector slugs.

### Patch a collection

`PATCH` is partial. `fields` is applied by **diff** (fields matched by name; omitted fields are
removed; existing values survive untouched fields). A `note` records a version snapshot.

```bash
curl -sX PATCH http://localhost:10040/api/v1/collections/7f1c9d2e-... \
  -H "Content-Type: application/json" \
  -d '{"max_file_size_bytes": 104857600, "note": "raise upload ceiling to 100 MB"}'
```

### Collection health

`GET /api/v1/collections/{collection_id}/health` — capability `read`. An on-demand operational probe
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

`GET /api/v1/collections/{collection_id}/storage` — capability `read`. Measures how much hardware a
collection occupies, per store, plus a per-document breakdown sorted heaviest-first (so it doubles as
a top-N). Computed with grouped SQL aggregates and one Qdrant profile — no per-document N+1, no
cache.

| Field | Meaning |
|---|---|
| `s3` | **Exact** bytes: `{original_bytes, rendered_bytes, total_bytes, physical_unique_bytes, estimated:false}` |
| `postgres` | **Estimated** row bytes per bucket (documents / ir_blocks / enrichment / chunks / metadata / observability) + `total_bytes` |
| `qdrant` | **Estimated** `{points, dense_bytes, sparse_bytes, payload_bytes, total_bytes}` |
| `grand_total_bytes` | S3 (logical) + Postgres + Qdrant |
| `documents[]` | Per-document `{document_id, filename, s3, postgres, qdrant, total_bytes}` |

Only S3 is exact (it reads the content-addressed blob registry, and `physical_unique_bytes` accounts
for dedup). Postgres bytes come from `pg_column_size` and exclude index/TOAST/bloat; Qdrant bytes are
count-based arithmetic and exclude index overhead. Every footprint carries an `estimated` flag saying
which it is — the numbers are never presented as measured when they are not.

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

### Re-ingest a document

`POST /api/v1/documents/{document_id}/reingest` — capability `write`. Re-runs the pipeline on a
document that is **already stored**, instead of delete-and-re-upload (re-uploading the same bytes is
refused as a duplicate). The worker refetches the original by its content hash and re-processes it
with the collection's **current** pipeline, so this is how you apply a config change to existing
documents.

| Query param | Type | Default | Meaning |
|---|---|---|---|
| `force` | bool | `false` | Bypass the stage cache and recompute every stage from scratch. Use after a code change that did not bump a node's cache version. |

```bash
curl -sX POST "http://localhost:10040/api/v1/documents/d4c3.../reingest?force=true"
```

Response is an `UploadAccepted` (`202`) — `{document_id, job_id, duplicate}` — poll the job (§7). The
run is idempotent: the previous chunks/IR/pages are purged and the vectors overwritten, while the
user-declared metadata survives.

- `404` when the document is unknown.
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
| `GET` | `/api/v1/collections/{collection_id}/documents` | `read` | Document catalogue (newest first) |
| `GET` | `/api/v1/documents/{document_id}` | `read` | Full facts + resolved doc-level metadata |
| `GET` | `/api/v1/documents/{document_id}/pages` | `read` | Pages, in order (geometry + render blob ref) |
| `GET` | `/api/v1/documents/{document_id}/ir` | `read` | The full canonical IR (large) |
| `GET` | `/api/v1/documents/{document_id}/provenance` | `read` | Ingestion provenance — the parser/model pipeline (per-stage trace) that produced the IR + chunks |
| `GET` | `/api/v1/documents/{document_id}/chunks` | `read` | Chunks (enriched text, block ids, metadata) |
| `GET` | `/api/v1/documents/{document_id}/markdown` | `read` | Markdown view, generated on the fly from the IR |
| `GET` | `/api/v1/documents/{document_id}/html` | `read` | HTML view, generated on the fly from the IR |
| `DELETE` | `/api/v1/documents/{document_id}` | `write` | Delete everywhere (`204`) |

```bash
# List a collection's documents
curl -s http://localhost:10040/api/v1/collections/7f1c9d2e-.../documents

# One document's detail
curl -s http://localhost:10040/api/v1/documents/d4c3...
```

A `DocumentListItem` carries `id, filename, format, status` (`pending`/`processing`/`done`/
`failed`), `page_count`, `file_size`, `created_at`, `title`, `language`, `enabled`.

`DocumentDetail` adds `collection_id`, `mime_type`, `source_kind`, `source_hash`,
`pdf_blob_hash`, `simhash`, `pipeline_version`, and a `metadata` array of resolved
`{field_name, value, origin}` values.

`ChunkInfo` carries `id, chunk_index, text, token_count, is_indexed, role, enabled, strategy,
parent_id, block_ids[], metadata[]`. Pages (`PageInfo`) reference a `render_blob_hash` you fetch
via §8.

> The IR payload (`/ir`) is the whole canonical document (blocks, tables, figures, enrichments)
> and can be large — fetch it deliberately.

### Document views (markdown / HTML)

`GET /api/v1/documents/{document_id}/markdown` and `GET /api/v1/documents/{document_id}/html` —
capability `read`. Both render the document's **canonical IR** into a view format on the fly (the
IR is canonical; markdown/HTML are always generated, never stored sources — §"Non-negotiables").

| Query param | Type | Default | Meaning |
|---|---|---|---|
| `download` | bool | `false` | Truthy → `Content-Disposition: attachment; filename="<stem>.md"` (or `.html`). Falsy → inline (renders in a browser tab). |

```bash
# Inline in a browser
curl -s http://localhost:10040/api/v1/documents/d4c3.../markdown

# Force a download with the right filename
curl -s "http://localhost:10040/api/v1/documents/d4c3.../html?download=true" -O -J
```

Responses are `text/markdown` and `text/html` respectively. `404` when the document is unknown,
`403` when it belongs to a collection outside the caller's scope, `422` on a malformed document
UUID.

### The document grid & bulk operations

The catalogue route above is the simple newest-first listing. At 10k–100k+ documents you want the
**grid**: a filtered, sorted, paginated query plus bulk actions that take the *same* target model, so
"select all 5 000 matching, deselect 3, act on the rest" never enumerates ids client-side.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/documents/query` | `read` | `DocumentQueryResponse` — one page + the total match count |
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
  jobs}` (`202`) with one job handle per run; a match beyond `CORPUS_MAX_REINGEST_FANOUT` enqueues
  only the first N and reports `capped: true` with the full `matched`.

---

## 6. Search

Hybrid retrieval over one collection. Runs **inline** in the request (sub-second, no queue).

`POST /api/v1/collections/{collection_id}/search` — capability `search`.

### SearchRequest

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | string | — | Natural-language query (non-blank). Embedded with the collection's own embedder. |
| `limit` | int (1–100) | `10` | Number of fused results. |
| `filters` | object/null | `null` | Constraints on **filterable** fields: a scalar → equality, a list → any-of, or a range mapping of `gte`/`gt`/`lte`/`lt` bounds → numeric or ISO-8601 datetime range (e.g. `{"published": {"gte": "2024-01-01", "lte": "2024-12-31"}}`). |
| `search_in` | list/null | `null` | Fields × modalities to query. `null` → content on both semantic + lexical. |

Each `search_in` entry is a **SearchTarget**: `{ "field": "content"|<metadata field>,
"semantic": bool, "lexical": bool }`. `field` defaults to `"content"` (the chunk body).

Gates (all `422`, before any spend): a filter naming a non-filterable field; a malformed or
misapplied range filter (a range on a non-range-typed field); a `search_in` target naming a vector
the collection never indexed (or a selection with no modality). `404` when the collection is
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
      "bbox": [0.12, 0.34, 0.88, 0.41],
      "block_locations": [
        {"page": 6, "bbox": [0.12, 0.34, 0.88, 0.41]}
      ]
    }
  ],
  "score_kind": "rrf_fusion",
  "debug_info": null
}
```

A hit self-cites so a UI needs no follow-up `GET /documents/{id}`: `filename` and `document_title`
(the human identity — `document_title` is `null` when no title was parsed/generated), `heading_path`
(the chunk's section ancestry, top-down; empty under no section), and `metadata` (the document's
filterable fields). `block_ids` are the IR blocks the chunk was assembled from; `page` + `bbox`
locate the chunk's primary (leading) block and `block_locations` gives every source block's
`{page, bbox}` — all bboxes are `[x0, y0, x1, y1]` **normalised to [0, 1]** (multiply by the page
image size to draw), and `page`/`bbox` are `null` (and `block_locations` empty) for an unlocated
chunk (e.g. a page-less document). `score` is the fused RRF score (higher is better). `score_kind`
(always present) names what the score represents — `rrf_fusion` (the default), `dbsf_fusion`, or
`cross_encoder_rerank` (when a reranker is enabled). It is rank-based, comparable only **within** one
response — a round `1.0000` on a tiny/single-doc corpus is normal, not a bug. `debug_info` is `null`
unless there is a non-fatal note.

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

---

## 7. Jobs

Ingestion status, plus a cancel control. The worker writes the rows; the API serves them (and can
request a cancellation).

| Method | Path | Cap | Returns |
|---|---|---|---|
| `GET` | `/api/v1/jobs` | `read` | Jobs — a collection's (`?collection_id=`) or fleet-wide, filterable — a paginated `JobPage` |
| `GET` | `/api/v1/jobs/{job_id}` | `read` | One job's live state (poll this) |
| `GET` | `/api/v1/jobs/{job_id}/events` | `read` | Per-node execution trace, in order |
| `GET` | `/api/v1/jobs/{job_id}/stream` | `read` | Live progress as Server-Sent Events (see below) |
| `GET` | `/api/v1/jobs/workers/live` | `read` | What every worker is doing right now |
| `GET` | `/api/v1/jobs/queue` | `read` | Backlog depth — `{pending, running}` |
| `GET` | `/api/v1/jobs/cost?collection_id={id}` | `read` | A collection's paid text-gen roll-up (`CollectionCost`) |
| `GET` | `/api/v1/jobs/stage-durations?collection_id={id}` | `read` | Average per-stage wall-clock — the ETA basis (`StageDurations`) |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | `write` | Request cancellation of a queued/running job (`CancelResult`) |

> `collection_id` is **optional** on `GET /api/v1/jobs`. **Present** → scoped to that collection (and
> it scopes the key). **Omitted** → a **fleet-wide** listing across every collection (the "All Jobs"
> view), which is **full-access only**: a collection-scoped key must name a collection it owns, else
> `403` — the same gate `GET /api/v1/jobs/queue` applies to its fleet-wide counts. A **pending** job
> has `worker_id: null` (arq assigns the worker at claim time — never fabricated).

`GET /api/v1/jobs` is **paginated + filterable** (a collection — or the fleet — can hold thousands of
job rows). Query params:
- `collection_id` (optional) — scope to one collection, or omit for fleet-wide (see the note above).
- `status` (optional, **repeatable**) — filter to one or more of `pending`/`running`/`done`/`failed`/
  `cancelled` (e.g. `?status=pending&status=running`). Omit for all statuses.
- `order` (optional) — `newest` (default, `created_at` DESC — the monitoring view) or `oldest`
  (`created_at` ASC — **FIFO / "what runs next"**, typically paired with `status=pending`).
- `limit` (optional) — page size, clamped down to the server's `JOBS_MAX_PAGE_SIZE` (its default).
- `offset` (optional) — rows to skip for paging.

The response is a `JobPage` — `{ total, limit, offset, jobs }` where `total` is the full match count
(drives the pager), `limit`/`offset` echo the applied values, and `jobs` is the page in the requested
order (newest first by default).

A `JobStatus` carries `job_id, document_id, collection_id, status` (`queued`/`running`/`done`/
`failed`/`cancelled`), `progress` (0–100), `current_stage`, `error` (verbatim, only when failed),
`attempt`, `started_at`, `finished_at`, and `updated_at` (last progress write — freezes on a wedge).
It also joins display labels (`document_filename`, `document_title`, `collection_name`, each `null`
if the row is gone), a `cancel_requested` flag and a `stalled` flag (a RUNNING job idle past the
stall threshold — an early wedge warning), the paid-generation roll-up (`total_prompt_tokens`,
`total_completion_tokens`, `cost_usd`), the live fan-out counter (`items_done`/`items_total`, `null`
outside a fan-out stage), and — only on a failed job — a failure breadcrumb (`failed_node_id`,
`failed_node_kind`, `failed_item_index`, `error_type`).

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
each `JobEvent` has `stage, status` (`success`/`failed`/`skipped`), timestamps, `detail`).

`GET /api/v1/jobs/workers/live` returns running jobs grouped by worker (empty when idle).

### Live progress (Server-Sent Events)

`GET /api/v1/jobs/{job_id}/stream` — capability `read`. Prefer this over polling `GET /jobs/{id}` for
a live UI. The job is resolved and scope-checked **before** the stream opens, so an unknown id is a
normal `404` and never an error buried mid-stream.

The response is `text/event-stream`; each frame is `data: {...}\n\n` carrying a `kind`:

- `kind: "event"` — one newly-landed stage event (the same shape as a `JobEvent`), in execution order.
- `kind: "status"` — the full `JobStatus` snapshot, emitted only when it actually changes (so progress
  flows through without a per-tick spam of identical frames). A `{"kind": "status", "status": "gone"}`
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

---

## 8. Blobs

`GET /api/v1/blobs/{content_hash}` — capability `read`. Streams a content-addressed blob's raw
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
on a collection's `pipeline`/`search`. All require `read`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/pipelines` | Discover surfaces — one entry per pipeline (`ingest`, `search`) with its URLs |
| `GET` | `/api/v1/pipelines/{key}` | Lean design payload: palette + default blob + issues (`?full=true` for advanced blocks) |
| `POST` | `/api/v1/pipelines/{key}/inspect` | Build + validate + describe a posted blob |
| `POST` | `/api/v1/pipelines/{key}/edit` | Apply graph operations server-side, then inspect the result |
| `POST` | `/api/v1/pipelines/{key}/stages/view` | Stage view of a blob + validity (ingest-only) |
| `POST` | `/api/v1/pipelines/{key}/stages/apply` | Compile a stage action into the blob + view (ingest-only) |

`{key}` is `ingest` or `search`. An unknown key is `404`. The stage endpoints are **ingest-only**
today — an unknown OR non-stage pipeline key `404`s, and the discovery index omits the stage URLs
for pipelines with no stage rail.

Design philosophy: a malformed/invalid blob is returned as **data** (`valid: false` + `issues`,
or `build_error`/`edit_error`), never as an HTTP error — the editor renders the problems in place.

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
| `GET` | `/api/v1/collections/{collection_id}/snippets/{kind}` | `read` | Export one config facet as a `CollectionSnippet` |
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

## 11. Cost estimate (dry-run)

Before spending anything on ingestion, project the cost and volume of running a collection's
pipeline over its documents. This is a **pre-hoc estimate** — no job is enqueued, nothing is spent,
no writes happen. It reads the collection's **actual** pipeline config (only enabled cost-incurring
stages are costed) plus cheap per-document stats, then projects per-stage token/page usage and
dollar cost against the same rate model the post-hoc job meter uses.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/estimate` | `read` | A `CostEstimate` — per-stage breakdown + totals |

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

## 12. Collection transfers (portable `.dcexport` bundles)

Where a snippet (§10) moves one config facet, a **transfer** moves a **whole collection** — schema,
config, documents, IR, chunks and vectors — into a portable `.dcexport` bundle you can re-import on
another server with **no recompute** (ids are remapped on import, never preserved). Both directions
run **asynchronously**: the route returns `202` with a transfer handle you poll.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/collections/{collection_id}/export` | `read` | Start packaging a collection into a bundle (`202`) |
| `POST` | `/api/v1/collections/import` | `create` | Import an uploaded bundle as a **new** collection (`202`) |
| `GET` | `/api/v1/transfers/{transfer_id}` | `read` | Poll one transfer's live status |
| `GET` | `/api/v1/transfers/{transfer_id}/download` | `read` | Stream a finished export's bundle bytes |

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
| `GET` | `/api/v1/audit` | `read` + **full-access** | One newest-first, keyset-paginated page of the trail |

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

## 16. Errors

FastAPI's standard error envelope is used throughout:

```json
{ "detail": "Collection 7f1c9d2e-... not found." }
```

Request-validation errors (`422`) carry FastAPI's structured `detail` array:

```json
{ "detail": [ { "loc": ["body", "query"], "msg": "query must not be blank", "type": "value_error" } ] }
```

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
