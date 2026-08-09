# DocForge SDK — INGESTION, FORGED

**The typed Python client for [DocForge](https://github.com/Florian-BARRE/DocForge)** — async **and**
sync, fully type-hinted, zero server-tree dependency.

[![PyPI](https://img.shields.io/pypi/v/docforge-sdk?label=docforge-sdk&color=ef5b1e)](https://pypi.org/project/docforge-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/docforge-sdk?color=ef5b1e)](https://pypi.org/project/docforge-sdk/)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Florian-BARRE/DocForge/blob/main/src/docforge_sdk/LICENSE)

---

`docforge-sdk` is a typed Python client for the [DocForge](https://github.com/Florian-BARRE/DocForge)
REST API — a document-intelligence platform that melts any document (PDF, Office, images…) into a
canonical intermediate representation, enriches and chunks it, embeds it, and serves **hybrid
retrieval** over it.

The SDK ships **both** an asynchronous and a synchronous client with an identical surface, is fully
type-hinted (`py.typed`, Pydantic v2 models), and has **zero dependency on the DocForge server
tree** — it is a clean-room client that talks to the API over HTTP only (`httpx` + `pydantic` +
hand-written models mirroring the public REST contract), so it can be vendored or published
independently.

- ✅ **Async + sync** — the same methods with and without `await`.
- ✅ **Typed end to end** — request/response Pydantic models, no `dict`-spelunking.
- ✅ **Context-managed** — connection pooling via `async with` / `with`.
- ✅ **Typed errors** — one exception hierarchy for connection, auth, 404, 409, 422…
- ✅ **Tiny footprint** — only `httpx` and `pydantic`.

---

## Table of contents

- [Install](#install)
- [Requirements](#requirements)
- [Quickstart](#quickstart)
  - [Async](#async)
  - [Sync](#sync)
- [Authentication](#authentication)
- [Resources & methods](#resources--methods)
- [Recipes](#recipes)
  - [Create a collection](#create-a-collection)
  - [Upload a document and wait for ingestion](#upload-a-document-and-wait-for-ingestion)
  - [Hybrid search with filters](#hybrid-search-with-filters)
  - [Explore a document (pages, IR, chunks)](#explore-a-document-pages-ir-chunks)
  - [Manage API keys](#manage-api-keys)
- [Error handling](#error-handling)
- [Type hints & discoverability](#type-hints--discoverability)
- [Versioning & compatibility](#versioning--compatibility)
- [License](#license)
- [Publishing (maintainers)](#publishing-maintainers)

---

## Install

```bash
pip install docforge-sdk
```

## Requirements

- **Python 3.12+**
- A running DocForge API (self-hosted). The examples assume `http://localhost:10040`.
- An API token when the server has auth enabled (see [Authentication](#authentication)).

## Quickstart

### Async

```python
import asyncio

from docforge_sdk import AsyncClient, SearchRequest


async def main() -> None:
    async with AsyncClient("http://localhost:10040", api_token="df_root_...") as client:
        # Liveness
        print(await client.health.ping())

        # List collections
        collections = await client.collections.list()
        for c in collections:
            print(c.id, c.name)

        # Search the first one
        hits = await client.search.search(
            collections[0].id,
            SearchRequest(query="quarterly revenue", limit=5),
        )
        for hit in hits.hits:
            print(f"{hit.score:.3f}  {hit.text[:80]}")


asyncio.run(main())
```

### Sync

The synchronous client is the async one **without `await`** — same resources, same signatures.

```python
from docforge_sdk import Client, SearchRequest

with Client("http://localhost:10040", api_token="df_root_...") as client:
    collections = client.collections.list()
    hits = client.search.search(
        collections[0].id,
        SearchRequest(query="quarterly revenue", limit=5),
    )
    for hit in hits.hits:
        print(hit.score, hit.text)
```

Both clients accept the same constructor:

```python
AsyncClient(base_url: str, timeout: float = 30.0, api_token: str = "")
Client(base_url: str, timeout: float = 30.0, api_token: str = "")
```

| Argument | Default | Meaning |
|---|---|---|
| `base_url` | — | API origin, e.g. `"http://localhost:10040"`. |
| `timeout` | `30.0` | Per-request timeout in seconds. |
| `api_token` | `""` | Bearer token; empty means unauthenticated requests. |

> Always use the client as a context manager (`async with` / `with`) so the underlying HTTP
> connection pool is opened and closed cleanly. You *can* construct it directly, but then you own
> `await client.aclose()` / `client.close()`.

## Authentication

When the DocForge server runs with auth enabled, pass a bearer token as `api_token`. The token is
sent as `Authorization: Bearer <token>` on every request.

```python
client = AsyncClient("https://docforge.example.com", api_token="df_...")
```

Keys are **scoped**: a key carries a set of capabilities (`read`, `write`, `search`, `create`,
`admin`) and an optional allow-list of collection ids. The root token created at server bootstrap
has full access; mint narrower keys with [`client.auth`](#auth) (see [Manage API keys](#manage-api-keys)).

A key holding **`create`** may create new collections, and is **auto-granted ownership** of what it
creates: the new collection's id is appended to that key's own scope, so a single key can be given
"may create collections + full power over the ones it creates" without knowing ids in advance — the
natural setup for driving DocForge from an agent (e.g. over MCP). Pair it with a narrow,
`search`-only key scoped to one collection for your app's runtime.

## Resources & methods

Every resource hangs off the client (`client.<resource>.<method>(...)`). The async and sync surfaces
are identical.

### `health`
| Method | Returns | Purpose |
|---|---|---|
| `ping()` | `HealthStatus` | Liveness probe. |

### `collections`
| Method | Returns | Purpose |
|---|---|---|
| `list()` | `list[CollectionModel]` | Every collection. |
| `get(collection_id)` | `CollectionModel` | One collection (schema + pipelines). |
| `create(CreateCollectionRequest)` | `CollectionModel` | Create a collection (contract). |
| `update(collection_id, UpdateCollectionRequest)` | `CollectionModel` | Patch name / formats / fields / pipelines. |
| `delete(collection_id)` | `None` | Delete a collection. |
| `storage(collection_id)` | `CollectionStorageResponse` | Material storage footprint per store (S3 exact, Postgres/Qdrant estimated) + per-document breakdown. |

### `documents`
| Method | Returns | Purpose |
|---|---|---|
| `upload(collection_id, file, metadata=None, filename=None)` | `UploadAccepted` | Admit a document; returns the ingestion `job_id`. `file` is a path, `bytes`, or a `Path`. |
| `set_enabled(document_id, enabled)` | `DocumentEnabledResponse` | Reversibly hide/show a document from search. |

### `search`
| Method | Returns | Purpose |
|---|---|---|
| `search(collection_id, SearchRequest)` | `SearchResponse` | Hybrid (dense + sparse RRF) search, optional rerank. |

### `explorer`
| Method | Returns | Purpose |
|---|---|---|
| `list_documents(collection_id)` | `list[DocumentListItem]` | Documents in a collection. |
| `get_document(document_id)` | `DocumentDetail` | One document's detail. |
| `get_pages(document_id)` | `list[PageInfo]` | Page-level info. |
| `get_ir(document_id)` | `DocumentIRModel` | The canonical IR (blocks, tables, figures, enrichments). |
| `get_chunks(document_id)` | `list[ChunkInfo]` | The document's chunks. |
| `delete_document(document_id)` | `None` | Delete a document. |
| `set_chunk_enabled(chunk_id, enabled)` | `ChunkEnabledResult` | Toggle one chunk in/out of search. |
| `set_chunks_enabled(BulkChunkEnabledPatch)` | `BulkChunkEnabledResponse` | Toggle many chunks at once. |

### `jobs`
| Method | Returns | Purpose |
|---|---|---|
| `list(collection_id)` | `list[JobStatus]` | Ingestion jobs for a collection. |
| `get(job_id)` | `JobStatus` | One job's status + progress. |
| `get_events(job_id)` | `JobTrace` | Per-stage event trace. |
| `live_workers()` | `WorkersLive` | Currently active workers. |

### `blobs`
| Method | Returns | Purpose |
|---|---|---|
| `get(content_hash)` | `BlobContent` | Fetch a content-addressed blob (bytes + media type). |

### `auth`
| Method | Returns | Purpose |
|---|---|---|
| `create_key(name, permissions=None, expires_at=None)` | `CreatedKey` | Mint a key. The plaintext token is returned **once**. |
| `list_keys()` | `list[KeyInfo]` | Every key (metadata only, never the secret). |
| `rotate_key(key_id, ...)` | `CreatedKey` | Roll a key's secret. |
| `revoke_key(key_id)` | `None` | Revoke a key. |

### `pipelines`
Discovery + design surface for the ingestion / search graphs (advanced).

| Method | Returns | Purpose |
|---|---|---|
| `list_surfaces()` | `PipelineIndexResponse` | Available pipeline designs. |
| `get_design(key, full=True)` | `PipelineDesignResponse` | A design's palette + default blob. |
| `inspect(key, blob)` | `InspectResponse` | Validate a graph blob. |
| `edit(key, ...)` | `EditResponse` | Apply a structural edit to a blob. |
| `view_stages(key, blob)` | `StageViewResponse` | Compile a blob into the stage-rail view. |
| `apply_stage(key, ...)` | `StageApplyResponse` | Apply one stage-rail action. |

## Recipes

### Create a collection

A collection is a **contract**: a metadata schema + an ingestion pipeline + a search pipeline. The
pipelines default to the stock graphs when omitted.

```python
from docforge_sdk import Client, CreateCollectionRequest, FieldSpec, FieldType

with Client("http://localhost:10040", api_token="df_...") as client:
    collection = client.collections.create(
        CreateCollectionRequest(
            name="reports",
            supported_formats=["pdf", "docx"],
            max_file_size_bytes=50 * 1024 * 1024,
            fields=[
                FieldSpec(field_name="year", field_type=FieldType.INTEGER, filterable=True),
                FieldSpec(field_name="team", field_type=FieldType.KEYWORD_LIST, filterable=True),
            ],
        )
    )
    print(collection.id)
```

Key `CreateCollectionRequest` fields beyond the schema: `max_file_size_bytes` (bytes) and
`job_timeout_seconds` (`float | None`, seconds) — the whole-ingest-job wall-clock budget for that
collection; `None` (the default) inherits the worker's global job-timeout default. Same field, same
semantics on `CollectionModel` (read) and `UpdateCollectionRequest` (write; there, omitting it
leaves the current value unchanged, a set value overrides it).

### Upload a document and wait for ingestion

`upload` returns immediately with a `job_id`; ingestion runs asynchronously on the worker. Poll the
job until it reaches a terminal state.

```python
import time
from docforge_sdk import Client

with Client("http://localhost:10040", api_token="df_...") as client:
    accepted = client.documents.upload(
        collection_id,
        file="report-2024.pdf",
        metadata={"year": 2024, "team": ["finance"]},
    )

    while True:
        job = client.jobs.get(accepted.job_id)
        print(job.status, job.progress, job.current_stage)
        if job.status in {"done", "failed"}:
            break
        time.sleep(2)

    if job.status == "failed":
        raise RuntimeError(job.error)
```

The async variant is the same with `await` and `asyncio.sleep`.

### Hybrid search with filters

`SearchRequest` drives dense + sparse fusion (RRF), optional late-interaction rerank, and metadata
filtering.

```python
from docforge_sdk import Client, SearchRequest

with Client("http://localhost:10040", api_token="df_...") as client:
    resp = client.search.search(
        collection_id,
        SearchRequest(
            query="revenue guidance for next fiscal year",
            limit=10,
            filters={"year": 2024, "team": "finance"},
        ),
    )
    for hit in resp.hits:
        print(f"{hit.score:.3f}  doc={hit.document_id}  {hit.text[:100]}")
```

Key `SearchRequest` fields: `query` (required), `limit` (1–100, default 10), `filters`
(`dict[str, Any]`), `search_in` (`list[SearchTarget]` to pick which vectors to query).

### Explore a document (pages, IR, chunks)

```python
with Client("http://localhost:10040", api_token="df_...") as client:
    docs = client.explorer.list_documents(collection_id)
    doc = client.explorer.get_document(docs[0].document_id)

    ir = client.explorer.get_ir(doc.document_id)  # canonical IR
    chunks = client.explorer.get_chunks(doc.document_id)

    # Reversibly drop a noisy chunk out of search:
    client.explorer.set_chunk_enabled(chunks[0].chunk_id, enabled=False)
```

### Measure a collection's storage footprint

`storage` reports the material footprint per store — S3 bytes are exact (deduped), Postgres/Qdrant
bytes are estimates (each section flags this via its own `estimated`) — plus a per-document
breakdown sorted heaviest first.

```python
with Client("http://localhost:10040", api_token="df_...") as client:
    footprint = client.collections.storage(collection_id)
    print(footprint.grand_total_bytes, footprint.s3.physical_unique_bytes)
    for doc in footprint.documents[:5]:
        print(doc.filename, doc.total_bytes)
```

### Manage API keys

Mint a scoped, expiring key (the plaintext is shown **once**, on creation):

```python
from datetime import datetime, timedelta, timezone
from docforge_sdk import Client, Capability, KeyPermissions

with Client("http://localhost:10040", api_token="df_root_...") as client:
    created = client.auth.create_key(
        name="reporting-bot",
        permissions=KeyPermissions(
            capabilities=[Capability.READ, Capability.SEARCH],
            collections=[collection_id],  # empty list = all collections
        ),
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    print("SAVE THIS NOW:", created.key)  # plaintext, only returned once

    for key in client.auth.list_keys():
        print(key.id, key.name, key.last_used_at)
```

## Error handling

Every failure raises a subclass of `DocForgeError`, so you can catch broadly or precisely.

```python
from docforge_sdk import (
    Client,
    DocForgeError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthError,
    NotFoundError,
    ConflictError,
    UnprocessableError,
)

with Client("http://localhost:10040", api_token="df_...") as client:
    try:
        client.collections.get("does-not-exist")
    except NotFoundError:
        ...  # 404
    except AuthError:
        ...  # 401 / 403 — bad or unscoped token
    except UnprocessableError as e:
        ...  # 422 — validation errors (see e.status / e.detail)
    except APITimeoutError:
        ...  # request exceeded `timeout`
    except APIConnectionError:
        ...  # server unreachable
    except DocForgeError:
        ...  # catch-all
```

Hierarchy:

```
DocForgeError
├── APIConnectionError
│   └── APITimeoutError
└── APIStatusError            # any non-2xx (carries .status)
    ├── AuthError             # 401 / 403
    ├── NotFoundError         # 404
    ├── ConflictError         # 409
    └── UnprocessableError    # 422
```

## Type hints & discoverability

The package ships `py.typed`, so editors and type-checkers see every request/response type. All
public models are re-exported from the top level:

```python
from docforge_sdk import (
    # clients
    AsyncClient,
    Client,
    # collections
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
    FieldSpec,
    FieldType,
    CollectionStorageResponse,
    # documents / explorer
    UploadAccepted,
    DocumentDetail,
    DocumentListItem,
    ChunkInfo,
    PageInfo,
    DocumentIRModel,
    # search
    SearchRequest,
    SearchResponse,
    SearchHit,
    SearchTarget,
    # jobs
    JobStatus,
    JobTrace,
    JobEvent,
    WorkersLive,
    # auth
    Capability,
    KeyPermissions,
    CreateKeyRequest,
    CreatedKey,
    KeyInfo,
    # errors
    DocForgeError,
    AuthError,
    NotFoundError,
    ConflictError,
    UnprocessableError,
)
```

`from docforge_sdk import *` also works and pulls the full public surface.

## Versioning & compatibility

The SDK tracks the DocForge REST contract; a CI parity gate diffs the SDK models against the live
server's OpenAPI on every change, so a published version is coherent with the API it targets. Pin a
version in production:

```bash
pip install "docforge-sdk==0.3.0"
```

## License

MIT — see [LICENSE](LICENSE). This SDK is deliberately licensed **MIT even though the parent DocForge
repository is GPLv3**: it is a standalone, clean-room client (HTTP models only, no server code), so a
permissive per-directory license is intentional and lets any project depend on it freely.

## Publishing (maintainers)

Releases publish to PyPI via **Trusted Publishing (OIDC)** — there is no API token stored in the
repo. To cut a release, tag a commit with the `sdk-v<version>` prefix (the version must match
`docforge_sdk/_version.py`) and push the tag:

```bash
git tag sdk-v0.1.0
git push origin sdk-v0.1.0
```

The `.github/workflows/release-sdk.yml` workflow then builds and uploads the sdist + wheel.

**One-time PyPI setup** (done once by the maintainer, before the first release):

1. Reserve the project name `docforge-sdk` on PyPI.
2. Under the project's *Publishing* settings, add a **GitHub trusted publisher** with:
   - Owner: `Florian-BARRE`
   - Repository: `docforge`
   - Workflow name: `release-sdk.yml`
   - Environment: `pypi`
