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
4. returns the JSON the SDK gives back (Pydantic models serialized with `model_dump(mode="json")`) as **compact, non-indented JSON text** (token cost) - one serialisation choke point (`libs/compact_json.py`, applied to every tool at registration); `search_collection` is the one tool that defaults to plain text (below).

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
outputs are the (compact, non-indented) JSON returned by the REST API. **Unknown arguments are rejected**: every tool's
argument model is `extra="forbid"` (FastMCP would otherwise silently drop them), so a wrong
parameter name (e.g. `page=5` on a tool that has no `page`) fails with an explicit validation error
instead of quietly succeeding; each tool's advertised input schema carries `additionalProperties: false`.

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
| `list_collections` | List every collection (identity, limits, health, schema incl. field descriptions). **Lean by default**: the heavy `pipeline`/`search` blobs are omitted; `include_pipelines=true` opts in. |
| `get_collection` | Return one collection's contract (identity, `title_field`, schema — which fields are filterable/semantic/lexical, with descriptions). **Lean by default** (no `pipeline`/`search` blobs, which weigh tens of thousands of characters); `include_pipelines=true` opts in. |
| `describe_collection` | **Call this FIRST before searching a collection**: fields (meaning, type, real example values), valid `search_in` targets, the filter grammar and ready-to-use example requests (`GET /collections/{id}/describe`). Never includes pipeline/search config or secrets. |
| `create_collection` | Create a collection A-to-Z: `name`, `supported_formats`, `max_file_size_bytes`, `fields` (metadata schema), optional `pipeline` blob (omit for the product default) or `preset="light"` for a fast config-free pipeline, plus `job_timeout_seconds`/`trace_verbosity`/`title_field`; each field may carry a `description`. Call `get_collection_contract_schema` first for the exact enum vocabulary. |
| `update_collection` | Patch identity/limits, the schema (diffed by `field_name` — omitted = removed), and/or the `pipeline`/`search` config blobs. Schema changes flip `needs_reindex`. `title_field` sets the display-title field; `clear_title_field=true` clears it. Returns the lean collection (blobs echoed back only when this call edited `pipeline`/`search`; `create_collection` is lean too — read blobs with `get_collection(include_pipelines=true)`). |
| `delete_collection` | Delete a collection (irreversible). |
| `collection_storage_footprint` | Measure a collection's material footprint per store — S3 bytes exact (deduped), Postgres/Qdrant estimated — plus a per-document breakdown, heaviest first. |
| `estimate_collection_cost` | Dry-run cost/volume projection before spending anything (`collection_id`, `scope="pending"`, `document_ids=None`, `filter=None`). Defaults to pending (not-yet-ingested) documents; pass `document_ids` to estimate a specific selection, or `filter` (same shape as the documents-grid filter) for a corpus slice — either one overrides `scope`. Per-stage token/page + dollar breakdown; unpriced models come back with a null cost, never fabricated; any unpriced paid stage makes `total_cost_usd` null — report `total_cost_lower_bound_usd` as a minimum and relay the caveat naming the model + stage + override path. |
| `preview_pipeline` | Dry-run the ingestion pipeline on ONE already-ingested document and get a bounded preview WITHOUT persisting anything (`collection_id`, `document_id`, optional `blob` candidate, `max_chunks`). Returns an IR summary, the first N chunks, the run's actual metered cost and the full execution trace; a failed node is data (`ok=false` + `failed_node_id` + trace), never an error. Inline/synchronous — cannot parse pipelines whose deps (docling) live only in the worker image. |
| `submit_preview_job` | Submit an ASYNCHRONOUS worker-side dry-run preview on one document WITHOUT persisting anything (`collection_id`, `document_id`, optional `blob` candidate, `max_chunks`). The worker runs the FULL ingest graph with every dependency present (docling included), so it covers ALL pipelines — use it when `preview_pipeline` cannot. Returns a pollable `preview_id`. |
| `get_preview_job` | Poll an asynchronous dry-run preview by its id (`collection_id`, `preview_id`). The bounded report appears in `result` once `status` is `done` (a failed node is data there — `result.ok=false`); `status` `failed` means the worker job itself crashed/timed out; an unknown/expired id is a 404. |
| `export_collection_snippet` | Export one granular config facet (`collection_id`, `kind` ∈ `pipeline`\|`search`\|`schema`) as a portable `.dfsnippet` — secret-masked, config-only, synchronous (contrast with the async whole-collection `.dcexport`). |
| `apply_collection_snippet` | Apply a `.dfsnippet` (`collection_id`, `kind`, `snippet`) onto this collection. Secrets from a different collection arrive masked and must be re-entered before the graph can run. |
| `collection_health` | Zero-spend, on-demand provider-reachability sweep across the ingest AND search graphs, plus index/doc stats and a rolled-up verdict. No job enqueued, nothing billed. |
| `reingest_collection` | Re-run the full pipeline over a collection's corpus (`collection_id`, optional `document_ids` subset, `force`) — the collection-scoped bulk reingest. Capped fan-out, one job handle per enqueued run. Answers `409 rebuild_index_required` while the index lacks a named vector: run `rebuild_collection_index` first. |
| `rebuild_collection_index` | Rebuild a collection's vector index from its current schema, without re-embedding content (`collection_id`). Use it after a field was made semantic/lexical post-ingest (search `422` / reingest `409 rebuild_index_required`). Returns a `job_id` to follow with `wait_for_job`; the job's `document_id` is null. Uploads/reingests get `409 rebuild_index_active` while it runs. |

### Documents (upload / admission)

| Tool | Purpose |
|---|---|
| `upload_document` | Upload a local file into a collection and enqueue ingestion (async — poll `get_job`/`get_document`). `metadata` is validated against the collection schema. |
| `upload_document_bytes` | Upload by sending raw bytes (`content_base64`) instead of a server-local path — the remote-caller counterpart of `upload_document`, no filesystem/`MCP_UPLOAD_DIR` involved. |
| `set_document_enabled` | Toggle a document's searchability (reversible, no re-ingest). |
| `update_document_metadata` | Update a document's metadata VALUES in place (document-scope fields only); filterable changes are instant, semantic/lexical changes queue a background re-embed returning a `job_id` to poll. |

### Explorer (read-only browse)

Reading a document piecemeal (agent path): `get_document_outline` -> `get_document_markdown(pages=...)`
for a section, or `get_chunk_context(chunk_id)` around a search hit; `get_document_chunks` to walk
chunks page by page. Text outputs use ASCII ` | ` separators.

| Tool | Purpose |
|---|---|
| `list_documents` | A collection's documents, newest first - the browse catalogue (`limit`/`offset` to page). |
| `get_document` | One document's full facts + resolved document-level metadata. |
| `get_document_pages` | The document's pages in order — geometry, routing, render-blob reference. |
| `get_document_ir` | The full canonical **IR** — blocks, tables, figures, enrichments. Very large: to read, prefer the outline / chunks / context tools below. |
| `get_document_provenance` | Ingestion provenance — the parser/model pipeline (per-stage trace) that produced the IR + chunks. Large; about processing, not content. |
| `get_document_outline` | The document's table of contents - one indented line per heading with its 1-based page and first chunk id (`format="text"` default, `"json"` compact). The cheap first step to read a long document. |
| `get_chunk_context` | A chunk plus its neighbours (`before`/`after`, 0-5, default 1) - the #1 way to read around a search hit. Text: `[index*] p.N \| heading` + text, target marked `*`. |
| `get_document_chunks` | The retrieval chunks, **paginated** (`limit=20`, `offset=0`) and **without geometry** by default (`include_geometry=false`). Output starts `chunks A-B of TOTAL` (from `X-Total-Count`); `format="json"` gives `{total, offset, chunks}`. |
| `get_document_markdown` | The document as Markdown, generated on the fly from the IR. Prefer `pages` (1-based: `5`, `5-7`, `5,7-9`) - the whole document can be ~50k chars. |
| `get_document_html` | The document as HTML (same `pages` parameter). |
| `delete_document` | Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge). Irreversible. |
| `set_chunk_enabled` | Toggle one chunk's searchability (reversible, no re-embed). |
| `set_chunks_enabled` | Toggle several chunks to the same state in one call (multi-select). |

### Search

| Tool | Purpose |
|---|---|
| `search_collection` | Hybrid semantic + keyword search (dense + sparse fusion). **Typed parameters**: `filters` is `{field: value}` where value is a scalar (equality; strings case-insensitive), a list (any-of) or ONE operator object `{eq,in,not,not_in,contains,prefix,exists,gte,gt,lte,lt}` (e.g. `{"topic":{"not":"legal"}}`, `{"title":{"contains":"audit"}}`, `{"keywords":{"prefix":"AL"}}`, `{"year":{"gte":2023}}`; an unknown operator key is refused by the tool schema, a per-type-invalid one by the server with the valid operators; `describe_collection` lists each field's type); `search_in` is a list of `{field, semantic, lexical}` targets — both are documented in the tool's JSON schema, and the docstring tells the agent to call `describe_collection` first. Returns ranked hits (cite the 1-based `page_number` and `document_title`) plus `hints`: a filter value no document stores yields the closest stored values — read them before concluding nothing exists. **Lean by default** for agents: `return_fields` (omitted → `text, document_title, page_number, heading_path, score, metadata`; `chunk_id`/`document_id` always come back; explicit list overrides, `metadata.<field>` keeps one entry; **geometry** = pass `return_fields` including `block_locations`/`bbox`/`page` with `format="json"`), `group_by="document"` + `max_per_document` (1-10, default 1: diverse sources instead of one document repeated), and `format`: `"text"` (default) = a header `N hits for "<query>"` then per hit `[rank] <title> | p.<page_number> | <heading > path> | score <s> | doc <id> | chunk <id>`, an optional `meta: k=v; ...` line and the chunk text, then `Hint: ...` lines (never any geometry); `"json"` = the compact response holding only the requested keys. Per-request tuning (forwarded only when set): `min_score`, `rerank` (false skips the reranker, true requires it), `fusion` (`rrf`|`dbsf`), `debug` (text mode adds `fusion F / rerank R` to the citation line; json hits carry `fusion_score`/`rerank_score`). A blank query is refused - use `browse_chunks`. Text mode uses `" | "` separators (ASCII-only output for Windows consoles). |
| `browse_chunks` | List a document's / a filter's passages **in reading order, without a query** (`POST /collections/{id}/chunks/browse`): read "all passages of document X" (filter on its identifier field) or walk a process page by page. Same `filters` grammar as search; `limit` 1-200 (default 20); `return_fields` (default lean: text, document_title, page_number, heading_path, metadata). Text format = `[n] <title> \| p.<page_number> \| <heading > path> \| doc <id> \| chunk <id>` + text per chunk, then `next_cursor: <token>` (pass it back as `cursor` with the SAME filters) or `end of results`, then `Hint:` lines; `format="json"` = compact `{chunks,next_cursor,hints}`. |

### Jobs

| Tool | Purpose |
|---|---|
| `list_jobs` | A collection's ingestion jobs, newest first — includes `document_filename`, `collection_name`, `current_stage`, `cancel_requested`. Omit `collection_id` for a fleet-wide listing (full-access token only). |
| `get_failure_breakdown` | Aggregate recent FAILED jobs over a look-back window — top causes, by stage, by collection. |
| `get_new_failures` | Count (+ optionally list) jobs that FAILED since a cursor timestamp — the "N new failures since you last looked" signal. |
| `get_job_timeseries` | Hourly job trends (created/done/failed + reconstructed backlog) over a look-back window. |
| `get_job` | One ingestion job's live state — poll after an upload. |
| `wait_for_job` | Block (server-side poll with backoff) until a job reaches done/failed/cancelled or `timeout_s` elapses (capped at 240s), then return its current status. |
| `get_job_events` | The per-node execution trace (stage, status, timing, error), in order. |
| `get_job_event_payload` | One stage-event's FULL raw input/output payload (`slot`) — only populated when the collection uses `trace_verbosity="full"`. |
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
| `apply_pipeline_stage` | Compile a stage-level action into a blob you hold (stateless, nothing saved; always buildable); returns recompiled blob + stage view + issues. To edit a collection, prefer `apply_collection_stage`. |
| `apply_collection_stage` | Apply ONE stage action to a collection's STORED pipeline and save it (`collection_id`, `action`, `note=None`) — no full-blob round-trip. A `set_config` defaults to `mode="merge"` (only the sent keys change; null resets a key; the api_key is kept). Returns the masked stage view + `valid`/`issues`/`notices` + `persisted` (false = nothing saved: invalid or no-op). |

### Transfers (collection export / import)

A completed export bundle's bytes are **never** streamed back through a tool result (a bundle can be
multi-GB) — `get_export_download_ref` instead points the caller at the REST download endpoint.

| Tool | Purpose |
|---|---|
| `export_collection` | Open an asynchronous export of a whole collection into a portable `.dcexport` bundle. Returns the transfer handle (202) — poll `get_transfer`. |
| `import_collection` | Import a `.dcexport` bundle as a brand-new collection. `file_path` is read from the **MCP SERVER's own filesystem**, not the caller's local disk — a remote deployment must stage the bundle there first. Returns the transfer handle (202). |
| `import_collection_bytes` | Import by sending the bundle's raw bytes (`content_base64`) instead of a server-local path — the remote-caller counterpart of `import_collection` (small/medium bundles only; a multi-GB bundle should still use the path-based tool via `MCP_UPLOAD_DIR`). |
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

### Audit

| Tool | Purpose |
|---|---|
| `list_audit` | One keyset-paginated page of the audit trail, newest first — one row per mutating API action (who/what/target/outcome). Filter by actor (`actor_user_id`/`actor_key_id`), target (`target_type`+`target_id`), `correlation_id`, and an ISO-8601 time window (`created_from`/`created_to`); walk it with `cursor`. **ROOT / full-access keys only** (a collection-scoped key is rejected `403`). |


**Total: 78 tools** across 13 sections.

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
| `MCP_UPLOAD_DIR` | *(unset)* | **HTTP-only upload inbox.** The one local directory `upload_document`/`import_collection`'s `file_path` may resolve into over `streamable-http` (resolved path, symlinks followed, must stay inside it). Unset (default) refuses both tools outright over HTTP — there is no "read anything the container can see" fallback. Ignored on stdio, where `file_path` is any local path as before. See [Access control](#access-control). |

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

**`file_path` tools (`upload_document`, `import_collection`) are confined the same way.** Over
`streamable-http`, any caller holding a valid DocForge API key could otherwise make the MCP
container read an arbitrary file its OS user can see (e.g. `/proc/1/environ`) and exfiltrate it by
uploading it into their own collection. `PathGuard` (`src/mcp/libs/path_guard.py`) closes this: on
HTTP the resolved, symlink-followed path MUST stay inside `MCP_UPLOAD_DIR`, or the call is refused
before the SDK is ever invoked — with no inbox configured (the default), both tools are refused
outright. Stdio is unaffected: `file_path` there is still any local path the caller names.

Operational checklist for a networked (streamable-http) deployment:
- Front the port with TLS (reverse proxy) — the caller's DocForge API key rides in the
  `Authorization` header on every call.
- Never expose port `10048` without a reason to trust every caller on the network path to it.
- Set `DOCFORGE_API_TOKEN` (the stdio fallback) to a **non-root, narrowly-scoped** key, or leave it
  empty — it is not read on the request path in HTTP mode, but an unused root token sitting in the
  service's env is still a needless blast-radius increase if ever misconfigured or reused elsewhere.
- If `upload_document`/`import_collection` are needed over HTTP, set `MCP_UPLOAD_DIR` to a dedicated
  staging directory (e.g. a shared volume) and mount it read-only where possible; otherwise leave it
  unset so those two tools stay refused.

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

The client launches the process and speaks MCP over stdio; the model can then call any of the 76
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
- Tool outputs are exactly the (compact) JSON the SDK returns — so anything you can do with the Python SDK,
  the model can do through MCP, and the two stay in lockstep (the SDK is held to the backend's
  OpenAPI contract by the CI [coherence gate](architecture.md#6-quality-gates)).

In short: **REST API → `docforge-sdk` typed client → MCP tools → your AI model.**
