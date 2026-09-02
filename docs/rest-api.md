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
| Collections | `/api/v1/collections` | §3 |
| Documents (admission) | `/api/v1/documents` | §4 |
| Explorer (browse) | `/api/v1/collections/{id}/documents`, `/api/v1/documents/{id}/...`, `/api/v1/chunks/...` | §5 |
| Search | `/api/v1/collections/{id}/search` | §6 |
| Jobs | `/api/v1/jobs` | §7 |
| Blobs | `/api/v1/blobs/{hash}` | §8 |
| Pipelines (design) | `/api/v1/pipelines` | §9 |
| Cost estimate (dry-run) | `/api/v1/collections/{id}/estimate` | §10 |
| Audit trail | `/api/v1/audit` | §11 |
| Idempotency (request header) | `Idempotency-Key` on mutating routes | §12 |
| Request correlation (response header) | `X-Request-Id` on every response | §13 |

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

---

## 3. Collections

A collection is the **contract**: a metadata schema + an ingestion pipeline blob + a search
config blob. The vector space is fixed at creation (named vectors cannot be added to Qdrant
later), so declare the **full** schema up front.

| Method | Path | Cap | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/collections` | `read` | List all collections with their schema |
| `GET` | `/api/v1/collections/{id}` | `read` | One collection's full contract |
| `POST` | `/api/v1/collections` | `create` | Create a collection (`201`); a scoped creator is auto-granted ownership of it |
| `PATCH` | `/api/v1/collections/{id}` | `write` | Patch identity/limits/schema/config |
| `DELETE` | `/api/v1/collections/{id}` | `write` | Delete a collection (`204`) |

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
| `GET` | `/api/v1/documents/{document_id}/chunks` | `read` | Chunks (enriched text, block ids, metadata) |
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

---

## 6. Search

Hybrid retrieval over one collection. Runs **inline** in the request (sub-second, no queue).

`POST /api/v1/collections/{collection_id}/search` — capability `search`.

### SearchRequest

| Field | Type | Default | Meaning |
|---|---|---|---|
| `query` | string | — | Natural-language query (non-blank). Embedded with the collection's own embedder. |
| `limit` | int (1–100) | `10` | Number of fused results. |
| `filters` | object/null | `null` | Constraints on **filterable** fields: a scalar → equality, a list → any-of. |
| `search_in` | list/null | `null` | Fields × modalities to query. `null` → content on both semantic + lexical. |
| `use_late_interaction` | bool/null | `null` | Opt into the ColBERT re-score. `null` → off. |
| `rescore_pool_size` | int (1–1000)/null | `null` | Fused candidate pool the ColBERT stage re-scores. `null` → node/store default. |

Each `search_in` entry is a **SearchTarget**: `{ "field": "content"|<metadata field>,
"semantic": bool, "lexical": bool }`. `field` defaults to `"content"` (the chunk body).

Gates (all `422`, before any spend): a filter naming a non-filterable field; a `search_in`
target naming a vector the collection never indexed (or a selection with no modality).
`404` when the collection is unknown; `409` when it has no embed node wired.

If `use_late_interaction` is requested but the collection carries no ColBERT vectors, the search
gracefully degrades to standard hybrid and notes it in `debug_info` (never a `500`).

### SearchResponse

```json
{
  "query": "termination clause",
  "hits": [
    {
      "chunk_id": "c1...",
      "document_id": "d4c3...",
      "score": 0.0731,
      "text": "Either party may terminate ...",
      "chunk_index": 12,
      "token_count": 148
    }
  ],
  "debug_info": null
}
```

`score` is the fused RRF score (higher is better). `debug_info` is `null` unless there is a
non-fatal note (e.g. `late_interaction_skipped`).

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

Read-only ingestion status. The worker writes the rows; the API only serves them.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `GET` | `/api/v1/jobs?collection_id={id}` | `read` | A collection's jobs, newest first |
| `GET` | `/api/v1/jobs/{job_id}` | `read` | One job's live state (poll this) |
| `GET` | `/api/v1/jobs/{job_id}/events` | `read` | Per-node execution trace, in order |
| `GET` | `/api/v1/jobs/workers/live` | `read` | What every worker is doing right now |

> `collection_id` is a **required query param** on `GET /api/v1/jobs` (it also scopes the key).

A `JobStatus` carries `job_id, document_id, collection_id, status` (`queued`/`running`/`done`/
`failed`), `progress` (0–100), `current_stage`, `error` (verbatim, only when failed), `attempt`,
`started_at`, `finished_at`.

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

## 10. Cost estimate (dry-run)

Before spending anything on ingestion, project the cost and volume of running a collection's
pipeline over its documents. This is a **pre-hoc estimate** — no job is enqueued, nothing is spent,
no writes happen. It reads the collection's **actual** pipeline config (only enabled cost-incurring
stages are costed) plus cheap per-document stats, then projects per-stage token/page usage and
dollar cost against the same rate model the post-hoc job meter uses.

| Method | Path | Cap | Returns |
|---|---|---|---|
| `POST` | `/api/v1/collections/{id}/estimate` | `read` | A `CostEstimate` — per-stage breakdown + totals |

The body is optional; when omitted, `scope` defaults to `pending`.

```json
{ "scope": "pending" }
```

- `scope` (`"pending"` \| `"all"`, default `"pending"`) — which documents to estimate over.
  `pending` covers uploaded-but-not-yet-ingested documents (the usual "what will this ingest cost?"
  preview); `all` covers every document in the collection (the cost of a full reingest).

The response is a `CostEstimate`: a per-stage breakdown, the projected volume, the totals, plus the
**assumptions** it rests on (chunk sizing taken from the collection's chunker config) and any
caveats. A stage whose model has no known rate is reported with a **null cost** (its token/page
volume is still shown) — never a fabricated number.

```bash
curl -s -X POST http://localhost:10040/api/v1/collections/$CID/estimate \
  -H 'content-type: application/json' -d '{"scope":"all"}'
```

`404` when the collection is unknown; `422` when its stored pipeline blob is unreadable (mirrors
the reingest error contract).

---

## 11. Audit trail

An append-only log of every **mutating** `/api/v1` request (`POST`/`PUT`/`PATCH`/`DELETE`). A
middleware records exactly one row per routed mutating request **after** the response is sent
(fail-safe — an audit write can never delay or fail the user's request); reads and non-API paths
are never audited. Each row captures the actor, the low-cardinality route **template** (not the
raw-id path), the final response status, the target resource (type + id parsed from the path), the
client IP, and the request's correlation id (see §13).

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
| `correlation_id` | Filter to one request's correlation id (see §13) |
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

## 12. Idempotency (`Idempotency-Key`)

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

## 13. Request correlation (`X-Request-Id`)

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
  (§11) to pull the audit row for that request.

```bash
curl -s -D - -o /dev/null http://localhost:10040/api/v1/collections | grep -i x-request-id
# X-Request-Id: 6b1f...   (echo an inbound one: -H 'X-Request-Id: my-trace-42')
```

---

## 14. Errors

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
| `400` / `422` | Validation failure — bad body, blank query, unknown metadata field, non-filterable filter, invalid search target, unmigratable/invalid pipeline blob, or an `Idempotency-Key` reused with a different body (§12). |
| `401` | Auth on and the bearer is missing/invalid/revoked/expired (carries `WWW-Authenticate: Bearer`). |
| `403` | Authenticated but lacking the capability, not scoped to the target collection/resource, or a scoped key on the full-access audit trail (§11). |
| `404` | Unknown collection / document / chunk / job / blob / pipeline key. |
| `409` | Name clash (collection / key), rotating an already-revoked key, root not provisioned, a collection with no embed node on search, or an `Idempotency-Key` whose request is still in progress (§12). |
| `500` | Unexpected server error (opaque). |
