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
| `list_jobs` | A collection's ingestion jobs, newest first. |
| `get_job` | One ingestion job's live state — poll after an upload. |
| `get_job_events` | The per-node execution trace (stage, status, timing, error), in order. |
| `get_live_workers` | What every worker is doing right now, grouped by worker. |

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

**Total: 32 tools** across 9 domains.

---

## 3. Run it

The server dispatches on `MCP_TRANSPORT` (`src/mcp/entrypoint.py`).

### Configuration (`src/mcp/config_loader.py`)

| Env var | Default | Purpose |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` (local) or `streamable-http` (container service). |
| `DOCFORGE_API_URL` | `http://localhost:8000` | Base URL of the DocForge REST API. |
| `DOCFORGE_API_TOKEN` | *(empty)* | Bearer token sent on every outbound API request when DocForge has `AUTH_ENABLED=true`. Must match the root key or a registered per-user key. Leave empty only against an auth-disabled instance. |
| `MCP_API_TIMEOUT_S` | `60` | Per-request timeout (seconds) for SDK HTTP calls. |
| `MCP_AUTH_TOKEN` | *(empty)* | Shared bearer the **HTTP** transport requires from clients. Empty is valid only in stdio mode — the server refuses to start HTTP without it. |
| `MCP_HOST` | `0.0.0.0` | Bind address for the HTTP transport. |
| `MCP_PORT` | `9000` | Internal HTTP listen port. |
| `MCP_HTTP_PATH` | `/mcp` | URL path the streamable-HTTP endpoint is served on. |

> Two distinct tokens: **`DOCFORGE_API_TOKEN`** authenticates the MCP server *to DocForge*;
> **`MCP_AUTH_TOKEN`** authenticates *clients to the MCP server* (HTTP transport only).

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

Set `MCP_AUTH_TOKEN` (and `DOCFORGE_API_TOKEN` if the API has auth on) in `services/mcp/.env`. The
endpoint is then reachable at `http://<host>:10048/mcp`, and every request must carry
`Authorization: Bearer <MCP_AUTH_TOKEN>` — a constant-time bearer check
(`StaticBearerAuthMiddleware`) rejects anything else with `401`. The HTTP app is stateless and
returns JSON responses, so it proxies cleanly.

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

The client launches the process and speaks MCP over stdio; the model can then call any of the 32
tools. (Use an absolute path to `entrypoint.py` if your client does not run from the repo root, and
run it through `uv`/the project venv so `docforge_sdk` and `mcp` are importable.)

### streamable-HTTP

For clients that support HTTP MCP, point them at `http://<host>:10048/mcp` and configure the bearer
header `Authorization: Bearer <MCP_AUTH_TOKEN>`. This is the deployment to use when the model and the
DocForge stack live on different hosts.

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
