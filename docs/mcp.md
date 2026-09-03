# DocForge MCP Server

Drive DocForge from an AI model. The MCP server exposes the **full DocForge REST surface** as
[Model Context Protocol](https://modelcontextprotocol.io) tools, so any MCP-capable client (Claude
Desktop, Claude Code, or your own agent) can manage collections, upload documents, inspect parsed
IR/chunks, run hybrid search, watch ingestion jobs, and even edit ingestion pipelines — end to end,
in natural language.

> **Related docs:** [Architecture](architecture.md) · [Getting started](getting-started.md) ·
> [REST API](rest-api.md) · [Python SDK](python-sdk.md) · [Pipeline reference](../src/docforge/PIPELINE.md)

---

## 1. What it is

The MCP server (`src/mcp/`) is a **thin, self-contained bridge**. It holds no domain logic and talks
to no database or object store — it is a pure HTTP client of the DocForge REST API, built on top of
the published [`docforge-sdk`](python-sdk.md) package. Each MCP tool is a small wrapper that:

1. accepts LLM-friendly dictionary/scalar arguments,
2. validates them into the SDK's typed request models,
3. calls the corresponding `docforge-sdk` resource method, and
4. returns the JSON the SDK gives back (Pydantic models serialized with `model_dump(mode="json")`).

Because it never imports the DocForge runtime config, it needs no Postgres/S3/Qdrant secrets — only
the API URL plus its own transport and auth knobs. An AI connected to it can therefore operate a
DocForge instance with exactly the capabilities its API key is scoped to.

The server surfaces a short instruction string to the connected model so it knows where to start:

> DocForge is a document intelligence platform. Use these tools to manage collections of documents,
> upload files, inspect their parsed pages/chunks/IR, and run hybrid semantic + keyword search over
> indexed content. Start with `list_collections`; only documents with status `done` are searchable.

---

## 2. The tool catalogue

All tools are registered over the SDK in `src/mcp/libs/tools/`. Tool inputs are plain dicts/scalars;
outputs are the JSON returned by the REST API.

### Health

| Tool | Purpose |
|---|---|
| `ping` | Check DocForge connectivity — returns `{"status": "ok"}` when the app is serving. |

### API keys (auth)

Root-owned key management. DocForge auth is **keys-only** — there is no login/users surface.

| Tool | Purpose |
|---|---|
| `create_api_key` | Create a new root-owned key. Plaintext key is returned **exactly once**; only its hash is stored. Optional `permissions` scope + ISO-8601 `expires_at`. |
| `list_api_keys` | List every key (active + revoked) with prefixes and metadata — never the plaintext or hash. |
| `revoke_api_key` | Soft-revoke a key (idempotent; record kept for audit). |
| `rotate_api_key` | Issue a fresh secret (optionally re-scoped) and revoke the old one; new plaintext returned once. |

### Collections

A collection is a **contract**: supported formats, size limit, and the full metadata schema (the
vector space is fixed at creation), plus optional ingestion/search pipeline blobs.

| Tool | Purpose |
|---|---|
| `list_collections` | List every collection with its full contract (schema, pipeline, search blobs). |
| `get_collection` | Return one collection's full contract — including which fields are filterable/semantic/lexical. |
| `create_collection` | Create a collection A-to-Z: `name`, `supported_formats`, `max_file_size_bytes`, `fields` (metadata schema), optional `pipeline` blob (omit for the product default). |
| `update_collection` | Patch identity/limits, the schema (diffed by `field_name` — omitted = removed), and/or the `pipeline`/`search` config blobs. Schema changes flip `needs_reindex`. |
| `delete_collection` | Delete a collection (irreversible). |
| `collection_storage_footprint` | Measure a collection's material footprint per store — S3 bytes exact (deduped), Postgres/Qdrant estimated — plus a per-document breakdown, heaviest first. |
| `estimate_collection_cost` | Dry-run cost/volume projection before spending anything (`collection_id`, `scope="pending"`, `document_ids=None`, `filter=None`). Defaults to pending (not-yet-ingested) documents; pass `document_ids` to estimate a specific selection, or `filter` (same shape as the documents-grid filter) for a corpus slice — either one overrides `scope`. Per-stage token/page + dollar breakdown; unpriced models come back with a null cost, never fabricated. |
| `export_collection_snippet` | Export one granular config facet (`collection_id`, `kind` ∈ `pipeline`\|`search`\|`schema`) as a portable `.dfsnippet` — secret-masked, config-only, synchronous (contrast with the async whole-collection `.dcexport`). |
| `apply_collection_snippet` | Apply a `.dfsnippet` (`collection_id`, `kind`, `snippet`) onto this collection. Secrets from a different collection arrive masked and must be re-entered before the graph can run. |

### Documents (upload / admission)

| Tool | Purpose |
|---|---|
| `upload_document` | Upload a local file into a collection and enqueue ingestion (async — poll `get_job`/`get_document`). `metadata` is validated against the collection schema. |
| `set_document_enabled` | Toggle a document's searchability (reversible, no re-ingest). |

### Explorer (read-only browse)

| Tool | Purpose |
|---|---|
| `list_documents` | A collection's documents, newest first — the browse catalogue. |
| `get_document` | One document's full facts + resolved document-level metadata. |
| `get_document_pages` | The document's pages in order — geometry, routing, render-blob reference. |
| `get_document_ir` | The full canonical **IR** — blocks, tables, figures, enrichments (can be large). |
| `get_document_chunks` | The retrieval chunks — enriched text, composition, generated metadata. |
| `get_document_markdown` | The document rendered as Markdown, generated on the fly from the canonical IR. |
| `get_document_html` | The document rendered as HTML, generated on the fly from the canonical IR. |
| `delete_document` | Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge). Irreversible. |
| `set_chunk_enabled` | Toggle one chunk's searchability (reversible, no re-embed). |
| `set_chunks_enabled` | Toggle several chunks to the same state in one call (multi-select). |

### Search

| Tool | Purpose |
|---|---|
| `search_collection` | Hybrid semantic + keyword search (dense + sparse fusion, optional ColBERT late-interaction re-score). Supports `filters` on filterable fields, `search_in` targets (`content` or metadata fields, semantic/lexical axes), `use_late_interaction`, `rescore_pool_size`. Returns ranked hits. |

### Jobs

| Tool | Purpose |
|---|---|
| `list_jobs` | A collection's ingestion jobs, newest first — includes `document_filename`, `collection_name`, `current_stage`, `cancel_requested`. |
| `get_job` | One ingestion job's live state — poll after an upload. |
| `get_job_events` | The per-node execution trace (stage, status, timing, error), in order. |
| `get_live_workers` | What every worker is doing right now, grouped by worker (each with `worker_name`). |
| `cancel_job` | Stop a job — cooperative by default (running job stops at its next stage boundary), or `force=true` to terminate immediately. |

### Blobs

| Tool | Purpose |
|---|---|
| `get_blob` | Fetch a content-addressed blob (page render, figure crop, canonical PDF, original upload). Images return as an inline MCP image; other mime types return base64 + `mime_type`. |

### Pipelines (design surface)

The graph JSON stays **opaque** at the tool boundary — blobs/operations/actions pass through as
plain dicts. See [`PIPELINE.md`](../src/docforge/PIPELINE.md) for what the graph means.

| Tool | Purpose |
|---|---|
| `list_pipeline_surfaces` | Discover the pipeline design surfaces (`ingest` / `search`) and their URLs. |
| `get_pipeline_design` | Open a surface: block palette, default blob, validation issues. `full=true` adds advanced blocks. |
| `inspect_pipeline` | Validate an edited blob without saving: validity, issues, and the described graph tree (or `build_error`). |
| `edit_pipeline` | Apply ordered graph operations server-side, then build + validate + describe the result. |
| `view_pipeline_stages` | Derive the ordered stage view of a blob + its validity verdict. |
| `apply_pipeline_stage` | Compile a stage-level action into a blob (always buildable); returns recompiled blob + stage view + issues. |

### Transfers (collection export / import)

A completed export bundle's bytes are **never** streamed back through a tool result (a bundle can be
multi-GB) — `get_export_download_ref` instead points the caller at the REST download endpoint.

| Tool | Purpose |
|---|---|
| `export_collection` | Open an asynchronous export of a whole collection into a portable `.dcexport` bundle. Returns the transfer handle (202) — poll `get_transfer`. |
| `import_collection` | Import a `.dcexport` bundle as a brand-new collection. `file_path` is read from the **MCP SERVER's own filesystem**, not the caller's local disk — a remote deployment must stage the bundle there first. Returns the transfer handle (202). |
| `get_transfer` | Poll a transfer's live status — progress, stage, counts, error, and (done) the artifact: bundle `size_bytes`/`expires_at` for an export, the new `collection_id`/`collection_name` for an import. |
| `get_export_download_ref` | For a done export, returns `size_bytes`/`expires_at` and the REST `download_path` to `GET` directly (or via `docforge_sdk`'s streaming `transfers.download_export`) — never the bundle bytes themselves. |


### Corpus grid & bulk operations

| Tool | Purpose |
|---|---|
| `query_documents` | One filtered/sorted/paginated page of a collection's documents + total match count (`collection_id`, `filter`, `sort`, `limit`, `offset`). Rows carry the catalogue fields + a `{field_name: value}` metadata map. |
| `delete_documents` | Bulk-delete by selector (`{document_ids:[…]}` XOR `{filter:{…}, exclude_ids:[…]}`) — everywhere (PG + Qdrant + S3). |
| `set_documents_enabled` | Bulk enable/disable searchability by selector (`enabled`). |
| `reingest_documents` | Bulk re-run the full ingestion by selector (`force`), capped fan-out, one job handle per run. |

### Jobs telemetry & introspection

| Tool | Purpose |
|---|---|
| `get_collection_cost` | Paid text-gen roll-up (tokens + USD) for a collection. |
| `get_queue_depth` | Backlog counters (pending/running) — fleet-wide (root) or per-collection. |
| `get_stage_durations` | Average per-stage wall-clock for a collection (a running job's ETA basis). |
| `reingest_document` | Re-run the full ingestion of a single document (`force`). |
| `get_collection_contract_schema` | JSON Schema of the collection identity/limits contract (build a valid create/update). |
| `whoami` | The calling token's own capabilities + collection scope — what it may do. |


**Total: 54 tools** across 10 domains.

---

## 3. Run it

The server dispatches on `MCP_TRANSPORT` (`src/mcp/entrypoint.py`).

### Configuration (`src/mcp/config_loader.py`)

| Env var | Default | Purpose |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` (local) or `streamable-http` (container service). |
| `DOCFORGE_API_URL` | `http://localhost:8000` | Base URL of the DocForge REST API. |
| `DOCFORGE_API_TOKEN` | *(empty)* | **stdio-only fallback bearer.** Used for every outbound API call when running over stdio (no `Authorization` header exists there to forward). In `streamable-http` mode this is **never** used to serve a request — see [Access control](#access-control) below. Leave empty only against an auth-disabled DocForge instance, and never set it to a root/admin key for a networked deployment. |
| `MCP_API_TIMEOUT_S` | `60` | Per-request timeout (seconds) for SDK HTTP calls. |
| `MCP_HOST` | `0.0.0.0` | Bind address for the HTTP transport. |
| `MCP_PORT` | `9000` | Internal HTTP listen port. |
| `MCP_HTTP_PATH` | `/mcp` | URL path the streamable-HTTP endpoint is served on. |

> There is no `MCP_AUTH_TOKEN` (removed) and no MCP-level auth gate of its own. The MCP is a pure
> pass-through: it forwards each caller's own DocForge API key, so one token gives the same rights
> on the REST API and via the MCP — see [Access control](#access-control).

> **Scoping the LLM's power.** The MCP can do exactly what the bearer it was given allows. Rather
> than a root key, prefer a dedicated **owner key** with capabilities `["read","write","search","create"]`
> and an empty collection scope: it may create collections and is auto-granted ownership of each one
> it creates (the new id is appended to its scope), so the agent can set up collections but can't
> touch anything it didn't make. For an app's runtime, mint a separate `search`-only key scoped to
> the one collection it uses.

### Access control

**The MCP has no auth of its own — it is a pass-through.** Every HTTP request presents the caller's
own DocForge API key in `Authorization: Bearer <docforge-api-key>`, forwarded upstream as-is, so the
caller gets exactly that key's scope on the REST API (`BearerPassthroughMiddleware` +
`ScopedSdkProvider` in `src/mcp/libs/`).

**An HTTP request with no bearer (missing, empty, or a non-`Bearer` scheme) is refused with 401
before any tool runs.** It never falls back to `DOCFORGE_API_TOKEN` or any other credential — that
fallback exists ONLY for the stdio transport, which has no Authorization header to forward in the
first place. This distinction matters: **MCP port `10048` IS published in production** (it's how AI
clients reach DocForge), so an unauthenticated request reaching it must be rejected, not silently
served with a privileged local token.

Operational checklist for a networked (streamable-http) deployment:
- Front the port with TLS (reverse proxy) — the caller's DocForge API key rides in the
  `Authorization` header on every call.
- Never expose port `10048` without a reason to trust every caller on the network path to it.
- Set `DOCFORGE_API_TOKEN` (the stdio fallback) to a **non-root, narrowly-scoped** key, or leave it
  empty — it is not read on the request path in HTTP mode, but an unused root token sitting in the
  service's env is still a needless blast-radius increase if ever misconfigured or reused elsewhere.

See also [PROD-HARDENING.md](PROD-HARDENING.md) for the full go-live checklist.

### (a) stdio — local clients

No network, no auth: the protocol runs over stdin/stdout, so logs are routed to stderr to keep the
JSON-RPC stream clean. Ideal for Claude Desktop / Claude Code on the same machine.

```bash
cd src/mcp
MCP_TRANSPORT=stdio \
DOCFORGE_API_URL=http://localhost:10040 \
DOCFORGE_API_TOKEN=<your-docforge-api-key> \
uv run python entrypoint.py
```

(Point `DOCFORGE_API_URL` at the dev API host port `10040`, or drop `DOCFORGE_API_TOKEN` entirely if
the target instance has auth disabled.)

### (b) streamable-HTTP — the compose service

The `docforge_mcp` service in `docker-compose.yml` runs the server as a long-lived HTTP
endpoint (under the `full` profile), pointing at the in-network API (`http://docforge_app:8000`) and
published on host port **`10048`**:

```bash
docker compose -f docker-compose.yml --profile full up -d docforge_mcp
```

The endpoint is then reachable at `http://<host>:10048/mcp`. There is **no separate MCP-level
token** — auth is delegated to DocForge: every request must carry
`Authorization: Bearer <docforge-api-key>`, which is forwarded upstream as-is, so a caller gets
**exactly the rights that key has on the REST API** (one token = same scope on the API and via the
MCP). **A request without a bearer is refused with 401** — it does NOT fall back to
`DOCFORGE_API_TOKEN`; that fallback is stdio-only (see [Access control](#access-control)). The HTTP
app is stateless and returns JSON responses, so it proxies cleanly. **Plain HTTP works out of the
box**; the key rides in the `Authorization` header, so on an untrusted network front the port with
TLS (a reverse proxy terminating HTTPS) — on a trusted LAN/VPN plain HTTP is fine.

---

## 4. Connect a client

### stdio (Claude Desktop / Claude Code / any MCP client)

Add an entry to your client's MCP config (`.mcp.json`-style):

```json
{
  "mcpServers": {
    "docforge": {
      "command": "python",
      "args": ["src/mcp/entrypoint.py"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "DOCFORGE_API_URL": "http://localhost:10040",
        "DOCFORGE_API_TOKEN": "<your-docforge-api-key>"
      }
    }
  }
}
```

The client launches the process and speaks MCP over stdio; the model can then call any of the 38
tools. (Use an absolute path to `entrypoint.py` if your client does not run from the repo root, and
run it through `uv`/the project venv so `docforge_sdk` and `mcp` are importable.)

### streamable-HTTP

For clients that support HTTP MCP, point them at `http://<host>:10048/mcp` and configure the bearer
header `Authorization: Bearer <your-docforge-api-key>` — the caller's own DocForge API key, not a
separate MCP-level secret (there isn't one; see [Access control](#access-control)). This is the
deployment to use when the model and the DocForge stack live on different hosts.

---

## 5. How it relates to the SDK

The MCP server is a **presentation layer over [`docforge-sdk`](python-sdk.md)**:

- `entrypoint.py` builds one `docforge_sdk.AsyncClient` (with `DOCFORGE_API_URL`, the timeout, and
  `DOCFORGE_API_TOKEN`) and injects it into every tool.
- Each tool module (`libs/tools/*.py`) maps a tool call to an SDK resource method
  (`sdk.collections.create`, `sdk.search.search`, `sdk.explorer.get_ir`, …), validating LLM dicts
  into the SDK's typed models (`CreateCollectionRequest`, `SearchRequest`, `KeyPermissions`, …)
  along the way.
- Tool outputs are exactly the JSON the SDK returns — so anything you can do with the Python SDK,
  the model can do through MCP, and the two stay in lockstep (the SDK is held to the backend's
  OpenAPI contract by the CI [coherence gate](architecture.md#6-quality-gates)).

In short: **REST API → `docforge-sdk` typed client → MCP tools → your AI model.**
