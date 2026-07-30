# DocForge Python SDK (`docforge-sdk`)

A typed Python client for the [DocForge](https://github.com/Florian-BARRE/docforge) REST API. It
ships **both** an asynchronous and a synchronous client with an identical surface, is fully
type-hinted (`py.typed`), and has **zero dependency on the DocForge server tree** — it is a
clean-room client that talks to the API over HTTP only.

---

## 1. Install

```bash
pip install docforge-sdk
```

- **Python 3.12+**.
- **Standalone**: the only runtime dependencies are [`httpx`](https://www.python-httpx.org/) (HTTP
  transport) and [`pydantic`](https://docs.pydantic.dev/) v2 (models + validation). No DocForge
  server code is imported, so the package can be vendored or installed anywhere.
- **Typed**: ships a `py.typed` marker; every method, argument and return value is annotated.
- **License**: MIT (deliberately permissive even though the parent DocForge repo is GPLv3 — this is
  a clean-room HTTP client with no server code).

---

## 2. Quickstart

The client takes the API **origin** as `base_url` (e.g. `http://localhost:10040` — port `10040` is
the DocForge dev API port). Pass `api_token` only when the target instance has authentication on
(see [§3](#3-authentication)). An optional `timeout` (seconds, default `30.0`) is also accepted.

Both clients expose the same resource groups and the same method signatures — the sync methods are
the async ones without `await`.

### Async — `AsyncClient`

```python
import asyncio

from docforge_sdk import AsyncClient


async def main() -> None:
    # Context-manager form auto-closes the underlying httpx client on exit.
    async with AsyncClient("http://localhost:10040", api_token="df_root_...") as client:
        health = await client.health.ping()
        print(health.status)  # "ok" when the app is serving

        collections = await client.collections.list()
        for collection in collections:
            print(collection.id, collection.name)


asyncio.run(main())
```

Manual close (no `async with`):

```python
client = AsyncClient("http://localhost:10040", api_token="df_root_...")
try:
    await client.health.ping()
finally:
    await client.aclose()
```

### Sync — `Client`

```python
from docforge_sdk import Client

# Context-manager form auto-closes on exit.
with Client("http://localhost:10040", api_token="df_root_...") as client:
    print(client.health.ping().status)
    for collection in client.collections.list():
        print(collection.id, collection.name)
```

Manual close (no `with`):

```python
client = Client("http://localhost:10040", api_token="df_root_...")
try:
    client.health.ping()
finally:
    client.close()
```

---

## 3. Authentication

DocForge instances can run with API-key auth on or off. When **on**, every request must carry a
bearer token: pass it once at construction as `api_token="df_..."` and the client attaches it to
every call. When auth is **off**, simply omit the argument (`api_token` defaults to `""`, meaning
unauthenticated requests). A wrong or missing token against an auth-enabled instance surfaces as an
[`AuthError`](#5-error-handling) (HTTP 401/403). API keys themselves are minted and managed through
the [`auth` resource](#auth--api-key-management).

Keys carry coarse **capabilities** — `Capability.READ`, `WRITE`, `SEARCH`, `CREATE`, `ADMIN` — plus a
collection scope (`["*"]` or explicit ids). A key holding `CREATE` may create collections and is
**auto-granted ownership** of what it creates (the new id is appended to its own scope), so one key
can be given "may create + full power over what it creates" without knowing ids up front — then mint
a narrow `SEARCH`-only key scoped to the resulting collection for your app.

---

## 4. Resource reference

The client wires nine resource groups onto itself: `auth`, `health`, `collections`, `documents`,
`explorer`, `search`, `jobs`, `blobs`, `pipelines`. Import any typed model straight from the package
root (`from docforge_sdk import SearchRequest, FieldSpec, ...`).

### `health` — liveness

| Method | Returns | Description |
|---|---|---|
| `health.ping()` | `HealthStatus` | Probe the API's liveness (`status == "ok"` when serving). |

```python
status = client.health.ping()
assert status.status == "ok"
```

### `collections` — collection CRUD

| Method | Returns | Description |
|---|---|---|
| `collections.list()` | `list[CollectionModel]` | List every collection with its full schema. |
| `collections.get(collection_id)` | `CollectionModel` | Fetch one collection's full contract. |
| `collections.create(request)` | `CollectionModel` | Create a collection from a `CreateCollectionRequest`. |
| `collections.update(collection_id, request)` | `CollectionModel` | Patch a collection with an `UpdateCollectionRequest` (only set fields are sent). |
| `collections.delete(collection_id)` | `None` | Delete a collection. |

A collection is a *contract*: its metadata schema (`fields`) and vector space are fixed at creation.
Each `FieldSpec` declares one metadata field and how it is indexed:

- `field_name` (str), `field_type` (`FieldType`: `string`, `integer`, `float`, `bool`,
  `keyword_list`, `datetime`, `enum`, `text`, `integer_list`, `float_list`, `text_list`)
- `required` (bool) — upload refused without it (user fields)
- `filterable` (bool) — present in the Qdrant payload, usable in search `filters`
- `lexical` (bool) — gets a sparse BM25 named vector
- `semantic` (bool) — gets a dense named vector
- `enum_values` (`list[str] | None`) — allowed values when `field_type` is `enum`
- `origin` (`FieldOrigin`: `user` / `system` / `generated`; default `user`)
- `scope` (`FieldScope`: `document` / `chunk`; default `document`)

```python
from docforge_sdk import (
    Client,
    CreateCollectionRequest,
    FieldSpec,
    FieldType,
    FieldScope,
)

with Client("http://localhost:10040", api_token="df_root_...") as client:
    collection = client.collections.create(
        CreateCollectionRequest(
            name="quarterly-reports",
            supported_formats=["pdf", "docx"],
            max_file_size_bytes=25 * 1024 * 1024,
            fields=[
                FieldSpec(
                    field_name="fiscal_year",
                    field_type=FieldType.INTEGER,
                    required=True,
                    filterable=True,
                ),
                FieldSpec(
                    field_name="department",
                    field_type=FieldType.ENUM,
                    enum_values=["finance", "sales", "ops"],
                    filterable=True,
                ),
                FieldSpec(
                    field_name="summary",
                    field_type=FieldType.TEXT,
                    semantic=True,
                    lexical=True,
                    scope=FieldScope.DOCUMENT,
                ),
            ],
            # pipeline omitted → the product-default ingest graph (all stages wired).
        )
    )
    print(collection.id, collection.needs_reindex)
```

To patch a collection, send an `UpdateCollectionRequest` — only the fields you set are transmitted:

```python
from docforge_sdk import UpdateCollectionRequest

client.collections.update(
    collection.id,
    UpdateCollectionRequest(max_file_size_bytes=50 * 1024 * 1024, note="raise size limit"),
)
```

> The `pipeline` and `search` fields on these models are the opaque engine graph blobs (plain
> `dict`). Leave them unset to keep the product defaults; edit them via the
> [`pipelines`](#pipelines--pipeline-discovery--design) resource.

### `documents` — admission + searchability

| Method | Returns | Description |
|---|---|---|
| `documents.upload(collection_id, file, metadata=None, filename=None)` | `UploadAccepted` | Upload a file (path, `Path` or raw `bytes`) for asynchronous ingestion. |
| `documents.set_enabled(document_id, enabled)` | `DocumentEnabledResponse` | Toggle a document's searchability (hides/reveals all its chunks). |

Upload is asynchronous: the call returns immediately with a `document_id` and a `job_id` you poll
via the [`jobs`](#jobs--ingestion-monitoring) resource. `UploadAccepted.duplicate` is `True` when the
exact content+pipeline was already ingested (the existing document is returned, `job_id == ""`, and
nothing is re-run).

```python
import time

from docforge_sdk import Client, DocumentStatus

with Client("http://localhost:10040", api_token="df_root_...") as client:
    accepted = client.documents.upload(
        collection_id=collection.id,
        file="/data/2024-q4.pdf",
        metadata={"fiscal_year": 2024, "department": "finance"},
    )
    print(accepted.document_id, accepted.job_id, accepted.duplicate)

    # Poll the ingestion job until it reaches a terminal state.
    if not accepted.duplicate:
        while True:
            job = client.jobs.get(accepted.job_id)
            print(job.status, job.progress, job.current_stage)
            if job.status in ("done", "failed"):
                break
            time.sleep(2)
        if job.status == "failed":
            raise RuntimeError(job.error)

    # Hide the document from search without deleting it (reversible).
    client.documents.set_enabled(accepted.document_id, enabled=False)
```

`metadata` values are keyed by `field_name` and validated against the collection's schema
server-side (required fields must be present, enum values must be allowed, etc.).

### `explorer` — read surface (documents, IR, chunks)

| Method | Returns | Description |
|---|---|---|
| `explorer.list_documents(collection_id)` | `list[DocumentListItem]` | List a collection's documents, newest first. |
| `explorer.get_document(document_id)` | `DocumentDetail` | One document's full facts + resolved document-level metadata. |
| `explorer.get_pages(document_id)` | `list[PageInfo]` | A document's pages (geometry, routing, render blob refs). |
| `explorer.get_ir(document_id)` | `DocumentIRModel` | The full canonical IR (blocks, tables, figures, enrichments). |
| `explorer.get_chunks(document_id)` | `list[ChunkInfo]` | A document's retrieval chunks. |
| `explorer.delete_document(document_id)` | `None` | Delete a document and everything derived from it. |
| `explorer.set_chunk_enabled(chunk_id, enabled)` | `ChunkEnabledResult` | Toggle one chunk's searchability. |
| `explorer.set_chunks_enabled(patch)` | `BulkChunkEnabledResponse` | Toggle several chunks at once (`BulkChunkEnabledPatch`). |

```python
docs = client.explorer.list_documents(collection.id)
detail = client.explorer.get_document(docs[0].id)
print(detail.title, detail.status, [(m.field_name, m.value) for m in detail.metadata])

ir = client.explorer.get_ir(docs[0].id)
print(len(ir.blocks), len(ir.tables), len(ir.figures), len(ir.enrichments))

chunks = client.explorer.get_chunks(docs[0].id)
print(chunks[0].chunk_index, chunks[0].role, chunks[0].enabled)
```

Bulk chunk toggle:

```python
from docforge_sdk import BulkChunkEnabledPatch

result = client.explorer.set_chunks_enabled(
    BulkChunkEnabledPatch(chunk_ids=[chunks[0].id, chunks[1].id], enabled=False)
)
print(result.results)     # one ChunkEnabledResult per known chunk
print(result.not_found)   # ids that did not resolve (skipped, not an error)
```

### `search` — hybrid search

| Method | Returns | Description |
|---|---|---|
| `search.search(collection_id, request)` | `SearchResponse` | Run a hybrid search over a collection; returns ranked, hydrated chunk hits. |

A `SearchRequest` carries the query and its knobs:

- `query` (str, required)
- `limit` (int, default `10`, 1–100) — number of fused results
- `filters` (`dict | None`) — exact / any-of constraints on **filterable** metadata fields
  (`{field: value}` or `{field: [values]}`)
- `search_in` (`list[SearchTarget] | None`) — which fields × modalities to query;
  `None` → `content` on both semantic and lexical (the default)
- `use_late_interaction` (`bool | None`) — opt into the ColBERT re-score; `None` → off
- `rescore_pool_size` (`int | None`, 1–1000) — candidate-pool size the ColBERT stage re-scores

Each `SearchTarget` names one field and its modalities:

- `field` (str, default `"content"` — the chunk body, or a metadata field name)
- `semantic` (bool) — query the field's dense vector
- `lexical` (bool) — query the field's sparse BM25 vector

```python
from docforge_sdk import Client, SearchRequest, SearchTarget

with Client("http://localhost:10040", api_token="df_root_...") as client:
    response = client.search.search(
        collection.id,
        SearchRequest(
            query="quarterly revenue growth",
            limit=5,
            filters={"fiscal_year": 2024, "department": ["finance", "sales"]},
            search_in=[
                SearchTarget(field="content", semantic=True, lexical=True),
                SearchTarget(field="summary", semantic=True),
            ],
            use_late_interaction=True,
        ),
    )
    print(response.query)
    for hit in response.hits:  # best first
        print(hit.score, hit.document_id, hit.chunk_index, hit.text[:80])
```

Each `SearchHit` exposes `chunk_id`, `document_id`, `score` (fused RRF score, higher is better),
`text`, `chunk_index` and `token_count`. `SearchResponse.debug_info` carries non-fatal diagnostics
(or `None` when there is nothing to report).

### `jobs` — ingestion monitoring

| Method | Returns | Description |
|---|---|---|
| `jobs.list(collection_id)` | `list[JobStatus]` | List a collection's jobs, newest first. |
| `jobs.get(job_id)` | `JobStatus` | Fetch one job's live status. |
| `jobs.get_events(job_id)` | `JobTrace` | The job's per-node execution trace, in run order. |
| `jobs.live_workers()` | `WorkersLive` | Everything running right now, grouped by worker. |

`JobStatus` exposes `status` (`queued` / `running` / `done` / `failed`), `progress` (0–100),
`current_stage`, `error` (set only when failed), `attempt`, `started_at`, `finished_at`. A
`JobTrace` holds an ordered list of `JobEvent` (`stage`, `status`, timings, `detail`).

```python
trace = client.jobs.get_events(accepted.job_id)
for event in trace.events:
    print(event.stage, event.status, event.detail)

live = client.jobs.live_workers()
for worker in live.workers:
    print(worker.worker_id, len(worker.jobs))
```

### `blobs` — content-addressed fetch

| Method | Returns | Description |
|---|---|---|
| `blobs.get(content_hash)` | `BlobContent` | Fetch a blob's raw bytes and its server-registered media type. |

`BlobContent` pairs `content` (`bytes`) with `mime_type` (`str`). Content hashes come from IR/detail
fields such as `DocumentDetail.pdf_blob_hash`, `PageInfo.render_blob_hash` or
`IRFigure.crop_blob_hash`.

```python
detail = client.explorer.get_document(docs[0].id)
if detail.pdf_blob_hash:
    blob = client.blobs.get(detail.pdf_blob_hash)
    print(blob.mime_type, len(blob.content))
    with open("view.pdf", "wb") as fh:
        fh.write(blob.content)
```

### `auth` — API-key management

| Method | Returns | Description |
|---|---|---|
| `auth.create_key(name, permissions=None, expires_at=None)` | `CreatedKey` | Create a key; returns its plaintext **once**. |
| `auth.list_keys()` | `list[KeyInfo]` | List keys — metadata only, never a secret. |
| `auth.rotate_key(key_id, name=..., permissions=..., expires_at=...)` | `CreatedKey` | Issue a fresh secret (optionally re-scoped) and revoke the old key. |
| `auth.revoke_key(key_id)` | `None` | Soft-revoke a key (idempotent). |

Scope a key with `KeyPermissions` (or pass `None` / omit for a full-access root key):

- `capabilities` (`list[Capability]`: `READ` / `WRITE` / `SEARCH` / `ADMIN`)
- `collections` (`list[str]`: `["*"]` for every collection, else explicit collection UUIDs)

```python
from datetime import datetime, timedelta, timezone

from docforge_sdk import Client, Capability, KeyPermissions

with Client("http://localhost:10040", api_token="df_root_...") as client:
    created = client.auth.create_key(
        name="ci-search-bot",
        permissions=KeyPermissions(
            capabilities=[Capability.READ, Capability.SEARCH],
            collections=[collection.id],
        ),
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    print(created.key)  # plaintext — shown ONCE, never recoverable afterwards

    for info in client.auth.list_keys():
        print(info.id, info.name, info.prefix, info.revoked_at)
```

**Rotation** preserves an "absent ≠ null" contract: an argument you *omit* (left as the default `...`)
is cloned from the source key, while an explicit `None` sets that field to its null meaning
(`permissions=None` → full access, `expires_at=None` → never expires).

```python
# Keep name + expiry, widen the scope only:
rotated = client.auth.rotate_key(
    created.id,
    permissions=KeyPermissions(capabilities=[Capability.READ, Capability.SEARCH], collections=["*"]),
)
print(rotated.key)          # new plaintext
client.auth.revoke_key(created.id)  # the old key (idempotent)
```

> `CreatedKey.permissions` and `KeyInfo.permissions` are returned as the server's opaque JSONB blob
> (`dict | None`, `None` = full access), not a structured `KeyPermissions`.

### `pipelines` — pipeline discovery + design

The graph JSON is **opaque** to the SDK: blobs, palettes, operations, actions and issues pass
through as plain `dict` / `list[dict]`; only the typed envelope (validity flags, errors, URLs) is
modelled. This resource backs the visual pipeline studio.

| Method | Returns | Description |
|---|---|---|
| `pipelines.list_surfaces()` | `PipelineIndexResponse` | Discover the available design surfaces. |
| `pipelines.get_design(key, full=True)` | `PipelineDesignResponse` | Open a pipeline's design payload (palette + blob + issues). |
| `pipelines.inspect(key, blob)` | `InspectResponse` | Validate an edited blob (validity + issues + described tree). |
| `pipelines.edit(key, blob, operations)` | `EditResponse` | Apply ordered graph operations server-side. |
| `pipelines.view_stages(key, blob)` | `StageViewResponse` | Derive the ordered stage view of a blob. |
| `pipelines.apply_stage(key, blob, action)` | `StageApplyResponse` | Compile a stage action into a blob. |

```python
index = client.pipelines.list_surfaces()
for surface in index.pipelines:
    print(surface.key, surface.title)

design = client.pipelines.get_design("ingest", full=True)
report = client.pipelines.inspect("ingest", design.blob)
print(report.valid, report.issues, report.build_error)
```

---

## 5. Error handling

Every failure the client can raise descends from `DocForgeError`, so a single `except` can catch
them all. The tree:

```
DocForgeError                     # base — catches everything below
├── APIConnectionError            # API unreachable (DNS, refused connection, network drop)
│   └── APITimeoutError           # request exceeded the configured timeout
└── APIStatusError                # a 4xx/5xx HTTP status  (.status_code: int, .body: Any)
    ├── AuthError                 # 401 / 403
    ├── NotFoundError             # 404
    ├── ConflictError             # 409
    └── UnprocessableError        # 422 (server-side validation failed)
```

`APIStatusError` (and its subclasses) carry `status_code` (int) and `body` (the parsed JSON error
payload when decodable, else raw text). Unmapped statuses raise a plain `APIStatusError`.

```python
from docforge_sdk import (
    Client,
    SearchRequest,
    DocForgeError,
    NotFoundError,
    AuthError,
    UnprocessableError,
    APITimeoutError,
    APIConnectionError,
)

with Client("http://localhost:10040", api_token="df_root_...") as client:
    try:
        hits = client.search.search(collection_id, SearchRequest(query="revenue"))
    except NotFoundError:
        print("that collection does not exist")
    except AuthError as exc:
        print("auth rejected:", exc.status_code, exc.body)
    except UnprocessableError as exc:
        print("invalid request body:", exc.body)
    except APITimeoutError:
        print("request timed out")
    except APIConnectionError:
        print("could not reach the API")
    except DocForgeError as exc:
        print("other DocForge failure:", exc)
```

---

## 6. Async vs sync

The two clients are **the same surface twice**: `AsyncClient` / `Async*` resources vs `Client` /
`Sync*` resources, with identical method names, arguments and return types. The only difference is
`await`.

- Use **`Client`** (sync) for scripts, notebooks and CLIs — it runs on a real, thread-free
  `httpx.Client` path, so there's no event loop to manage.
- Use **`AsyncClient`** (async) for concurrent applications (web backends, batch fan-out) where you
  want to overlap many requests on one event loop.

Both release their underlying `httpx` connection pool on context-manager exit
(`async with` / `with`) or when you call `aclose()` / `close()` explicitly.

---

## 7. Typed & drift-guarded

Every request and response is a Pydantic v2 model that mirrors the DocForge REST contract
field-for-field. These models are **not** imported from the server — they are hand-written mirrors
that keep the SDK standalone — so the repository enforces coherence in CI: the `sdk-parity`
(*SDK↔backend OpenAPI drift*) job in `.github/workflows/gate.yml` regenerates the backend's live
OpenAPI schema and runs `src/docforge_sdk/tests/check_schema_drift.py` against it. Any divergence
between the SDK models and the backend schema turns the gate **red**, so a drifting SDK can neither
merge nor publish.
